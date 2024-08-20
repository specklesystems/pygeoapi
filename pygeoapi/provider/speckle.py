# =================================================================
#
# Authors: Matthew Perry <perrygeo@gmail.com>
#
# Copyright (c) 2018 Matthew Perry
# Copyright (c) 2022 Tom Kralidis
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# =================================================================

from datetime import datetime
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from pygeoapi.provider.base import BaseProvider, ProviderItemNotFoundError
from pygeoapi.util import crs_transform


LOGGER = logging.getLogger(__name__)
HOST_APP = "pygeoapi"

class SpeckleProvider(BaseProvider):
    """Provider class for Speckle server data
    This is meant to be simple
    (no external services, no dependencies, no schema)
    at the expense of performance
    (no indexing, full serialization roundtrip on each request)
    Not thread safe, a single server process is assumed
    This implementation uses the feature 'id' heavily
    and will override any 'id' provided in the original data.
    The feature 'properties' will be preserved.
    TODO:
    * query method should take bbox
    * instead of methods returning FeatureCollections,
    we should be yielding Features and aggregating in the view
    * there are strict id semantics; all features in the input GeoJSON file
    must be present and be unique strings. Otherwise it will break.
    * How to raise errors in the provider implementation such that
    * appropriate HTTP responses will be raised
    """

    def __init__(self, provider_def):
        """initializer"""

        super().__init__(provider_def)

        if self.data is None:
            self.data = ""
            # raise ValueError(
            #    "Please provide Speckle project link as an argument, e.g.: 'http://localhost:5000/?limit=100000&https://app.speckle.systems/projects/55a29f3e9d/models/2d497a381d'"
            # )

        from subprocess import run
        from pygeoapi.provider.speckle_utils.patch.patch_specklepy import patch_specklepy

        try:
            import specklepy

        except ModuleNotFoundError:
            
            completed_process = run(
                [
                    self.get_python_path(),
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "specklepy==2.19.6",
                ],
                capture_output=True,
            )
            completed_process = run(
                [
                    self.get_python_path(),
                    "-m",
                    "pip",
                    "install",
                    "pydantic==1.10.17",
                ],
                capture_output=True,
            )

            if completed_process.returncode != 0:
                m = f"Failed to install dependenices through pip, got {completed_process.returncode} as return code. Full log: {completed_process}"
                print(m)
                print(completed_process.stdout)
                print(completed_process.stderr)
                raise Exception(m)

        patch_specklepy()
        
        # assign global values
        self.url: str = self.data # to store the value and check if self.data has changed
        self.speckle_url = self.url.lower().split("speckleurl=")[-1].split("&")[0].split("@")[0].split("?")[0]

        self.speckle_data = None
        self.model_name = ""

        self.crs = None
        self.crs_dict = None

        self.lat: float = 51.52486388756923
        self.lon: float = 0.1621445437168942
        self.north_degrees: float = 0


    def get_fields(self):
        """
         Get provider field information (names, types)
        :returns: dict of fields
        """

        fields = {}
        LOGGER.debug("Treating all columns as string types")

        if self.speckle_data is None:
            self._load()
            
        # check if the object was extracted
        if isinstance(self.speckle_data, Dict):
            if len(self.speckle_data["features"]) == 0:
                return fields

            for key, value in self.speckle_data["features"][0]["properties"].items():
                if isinstance(value, float):
                    type_ = "number"
                elif isinstance(value, int):
                    type_ = "integer"
                else:
                    type_ = "string"

                fields[key] = {"type": type_}
        return fields

    def _load(self, skip_geometry=None, properties=[], select_properties=[]):
        """Validate Speckle data"""

        from pygeoapi.provider.speckle_utils.crs_utils import create_crs_from_authid

        if self.data == "":
            return 
            raise ValueError(
                "Please provide Speckle project link as an argument, e.g.: http://localhost:5000/?limit=100000&speckleUrl=https://app.speckle.systems/projects/55a29f3e9d/models/2d497a381d"
            )

        if (
            isinstance(self.data, str)
            and "speckleurl=" in self.data.lower()
            and "projects" in self.data
            and "models" in self.data
        ):
            crs_authid = ""
            for item in self.data.lower().split("&"):

                # if CRS authid is found, rest will be ignored
                if "crsauthid=" in item:
                    crs_authid = item.split("crsauthid=")[1]
                elif "lat=" in item:
                    try:
                        self.lat = float(item.split("lat=")[1])
                    except:
                        pass
                        # raise ValueError(f"Invalid Lat input, must be numeric: {item.split('lat=')[1]}")
                elif "lon=" in item:
                    try:
                        self.lon = float(item.split("lon=")[1])
                    except:
                        pass
                        # raise ValueError(f"Invalid Lon input, must be numeric: {item.split('lon=')[1]}")
                elif "northdegrees=" in item:
                    try:
                        self.north_degrees = float(item.split("northdegrees=")[1])
                    except:
                        pass
                        # raise ValueError(f"Invalid NorthDegrees input, must be numeric: {item.split('northdegrees=')[1]}")

            # if CRS assigned, create one:
            if len(crs_authid)>3:
                create_crs_from_authid(self)

        # check if it's a new request (self.data was updated and doesn't match self.url)
        new_request = False
        if self.url != self.data:
            new_request = True
            self.url = self.data

        # check if self.data was updated OR if features were not created yet
        if (
            new_request is True
            or self.speckle_data is None
            or (
                isinstance(self.speckle_data, dict)
                and hasattr(self.speckle_data, "features")
                and len(self.speckle_data["features"]) > 0
                and not hasattr(self.speckle_data["features"][0], "properties")
            )
        ):
            self.speckle_data = self.load_speckle_data()
            self.fields = self.get_fields()

        # filter by properties if set
        if properties:
            self.speckle_data["features"] = [
                f
                for f in self.speckle_data["features"]
                if all([str(f["properties"][p[0]]) == str(p[1]) for p in properties])
            ]  # noqa

        # All features must have ids, TODO must be unique strings
        if isinstance(self.speckle_data, str):
            raise Exception(self.speckle_data)
        for i in self.speckle_data["features"]:
            # for some reason dictionary is changed to list of links
            try:
                i["properties"]
            except:
                self.speckle_data = None
                return self._load()

            if "id" not in i and self.id_field in i["properties"]:
                i["id"] = i["properties"][self.id_field]
            if skip_geometry:
                i["geometry"] = None
            if self.properties or select_properties:
                i["properties"] = {
                    k: v
                    for k, v in i["properties"].items()
                    if k in set(self.properties) | set(select_properties)
                }  # noqa

        return self.speckle_data

    @crs_transform
    def query(
        self,
        offset=0,
        limit=10,
        resulttype="results",
        bbox=[],
        datetime_=None,
        properties=[],
        sortby=[],
        select_properties=[],
        skip_geometry=False,
        q=None,
        **kwargs,
    ):
        """
        query the provider
        :param offset: starting record to return (default 0)
        :param limit: number of records to return (default 10)
        :param resulttype: return results or hit limit (default results)
        :param bbox: bounding box [minx,miny,maxx,maxy]
        :param datetime_: temporal (datestamp or extent)
        :param properties: list of tuples (name, value)
        :param sortby: list of dicts (property, order)
        :param select_properties: list of property names
        :param skip_geometry: bool of whether to skip geometry (default False)
        :param q: full-text search term(s)
        :returns: FeatureCollection dict of 0..n GeoJSON features
        """

        # TODO filter by bbox without resorting to third-party libs
        data = self._load(
            skip_geometry=skip_geometry,
            properties=properties,
            select_properties=select_properties,
        )
        if data is None:
            return {"features":[]}

        data["numberMatched"] = len(data["features"])

        if resulttype == "hits":
            data["features"] = []
        else:
            data["features"] = data["features"][offset : offset + limit]
            data["numberReturned"] = len(data["features"])

        return data

    @crs_transform
    def get(self, identifier, **kwargs):
        """
        query the provider by id
        :param identifier: feature id
        :returns: dict of single GeoJSON feature
        """

        all_data = self._load()
        # if matches
        for feature in all_data["features"]:
            if str(feature.get("id")) == identifier:
                return feature
        # default, no match
        err = f"item {identifier} not found"
        LOGGER.error(err)
        raise ProviderItemNotFoundError(err)

    def create(self, new_feature):
        """Create a new feature
        :param new_feature: new GeoJSON feature dictionary
        """

        raise NotImplementedError("Creating features is not supported")

    def update(self, identifier, new_feature):
        """Updates an existing feature id with new_feature
        :param identifier: feature id
        :param new_feature: new GeoJSON feature dictionary
        """

        raise NotImplementedError("Updating features is not supported")

    def delete(self, identifier):
        """Deletes an existing feature
        :param identifier: feature id
        """

        raise NotImplementedError("Deleting features is not supported")

    def __repr__(self):
        return f"<SpeckleProvider> {self.data}"

    def load_speckle_data(self: str):
        
        from specklepy.logging.exceptions import SpeckleException
        from specklepy.api import operations
        from specklepy.core.api.wrapper import StreamWrapper
        from specklepy.core.api.client import SpeckleClient
        from specklepy.logging.metrics import set_host_app
        from specklepy.transports.server import ServerTransport

        set_host_app(HOST_APP, "0.0.99")
        
        # get URL that will not trigget Client init
        url_proj: str = self.speckle_url.split("models")[0]
        wrapper: StreamWrapper = StreamWrapper(url_proj)

        # set actual branch
        wrapper.model_id = self.speckle_url.split("models/")[1].split("/")[0].split("&")[0]
        
        # get client by URL, no authentication
        client = SpeckleClient(host=wrapper.host, use_ssl=wrapper.host.startswith("https"))
        client.account.serverInfo.url = url_proj.split("/projects")[0]

        # get branch data
        stream = client.stream.get(
            id = wrapper.stream_id, branch_limit=100
        )

        if isinstance(stream, Exception):
            raise SpeckleException(stream.message+ ", "+ self.speckle_url)

        for br in stream['branches']['items']:
            if br['id'] == wrapper.model_id:
                branch = br
                break

        # set the Model name
        self.model_name = branch['name']

        commit = branch["commits"]["items"][0]
        objId = commit["referencedObject"]

        transport = ServerTransport(client=client, account=client.account, stream_id=wrapper.stream_id)
        if transport == None:
            raise SpeckleException("Transport not found")

        # data transfer
        try:
            commit_obj = operations.receive(objId, transport, None)
        except Exception as ex:
            # e.g. SpeckleException: Can't get object b53a53697a/f8ce82b242e05eeaab4c6c59fb25e4a0: HTTP error 404 ()
            raise ex

        client.commit.received(
            wrapper.stream_id,
            commit["id"],
            source_application="pygeoapi",
            message="Received commit in pygeoapi",
        )
        print(f"Rendering model '{branch['name']}' of the project '{stream['name']}'")

        speckle_data = self.traverse_data(commit_obj)
        speckle_data["project"] = stream['name']
        speckle_data["model"] = branch['name']

        return speckle_data

    def traverse_data(self, commit_obj):

        from specklepy.objects.geometry import Point, Line, Polyline, Curve, Mesh, Brep
        from specklepy.objects.GIS.CRS import CRS
        from specklepy.objects.GIS.layers import VectorLayer
        from specklepy.objects.GIS.geometry import GisPolygonElement
        from specklepy.objects.GIS.GisFeature import GisFeature
        from specklepy.objects.graph_traversal.traversal import (
            GraphTraversal,
            TraversalRule,
        )
        from pygeoapi.provider.speckle_utils.crs_utils import create_crs_from_wkt, create_crs_default, create_crs_dict
        from pygeoapi.provider.speckle_utils.coords_utils import reproject_bulk
        from pygeoapi.provider.speckle_utils.props_utils import assign_props, assign_missing_props
        from pygeoapi.provider.speckle_utils.converter_utils import assign_geometry
        from pygeoapi.provider.speckle_utils.display_utils import find_display_obj, set_default_color, assign_display_properties, get_display_units

        supported_classes = [GisFeature, GisPolygonElement, Mesh, Brep, Point, Line, Polyline, Curve]
        supported_types = [y().speckle_type for y in supported_classes]
        supported_types.extend([
            "Objects.Other.Revit.RevitInstance", 
            "Objects.BuiltElements.Revit.RevitWall", 
            "Objects.BuiltElements.Revit.RevitFloor", 
            "Objects.BuiltElements.Revit.RevitStair",
            "Objects.BuiltElements.Revit.RevitColumn",
            "Objects.BuiltElements.Revit.RevitBeam",
            "Objects.BuiltElements.Revit.RevitElement",
            "Objects.BuiltElements.Revit.RevitRebar"])

        # traverse commit
        data: Dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
            "model_crs": "-",
        }
        self.assign_coordinate_system_to_geojson(data)
        rule = TraversalRule(
            [lambda _: True],
            lambda x: [
                item
                for item in x.get_member_names()
                if isinstance(getattr(x, item, None), list)
                and (x.speckle_type.split(":")[-1] not in supported_types or isinstance(x, VectorLayer))
            ],
        )
        context_list = [x for x in GraphTraversal([rule]).traverse(commit_obj)]

        # iterate Speckle objects to get CRS, DisplayUnits, offsets, rotation
        crs = None
        displayUnits = None
        offset_x = 0
        offset_y = 0
        try:
            for item in [commit_obj] + commit_obj.elements:
                if (
                    crs is None
                    and hasattr(item, "crs")
                    and isinstance(item["crs"], CRS)
                ):
                    crs = item["crs"]
                    displayUnits = crs["units_native"]
                    offset_x = crs["offset_x"]
                    offset_y = crs["offset_y"]
                    self.north_degrees = crs["rotation"]
                    create_crs_from_wkt(self, crs["wkt"])

                    if self.crs.to_authority() is not None:
                        data["model_crs"] = f"{self.crs.to_authority()}, {self.crs.name} "
                    else:
                        data["model_crs"] = f"{self.crs.to_proj4()}"

                    break
        except AttributeError as ex:
            pass # old commit structure

        # if CRS not found, create default one and get model units for scaling
        if self.crs is None:
            create_crs_default(self)
        # if displayUnits not found, get from displayable object
        if displayUnits is None:
            displayUnits = get_display_units(context_list)

        create_crs_dict(self, offset_x, offset_y, displayUnits)

        # get coordinates in bulk
        all_coords = []
        all_coord_counts = []


        all_props = []
        set_default_color(context_list)

        print(f"Loading features..")
        time1 = datetime.now()
        for item in context_list:
            
            f_base = item.current
            f_id = item.current.id
            f_fid = len(data["features"]) + 1

            # initialize feature
            feature: Dict = {
                "type": "Feature",
                # "bbox": [-180.0, -90.0, 180.0, 90.0],
                "geometry": {},
                "properties": {
                    "id": f_id,
                    "FID": f_fid,
                    "speckle_type": item.current.speckle_type.split(":")[-1],
                },
            }

            # feature geometry, props and displayProps
            obj_display, obj_get_color = find_display_obj(f_base)
            coords, coord_counts = assign_geometry(feature, obj_display)
            if len(coords)!=0:
                all_coords.extend(coords)
                all_coord_counts.append(coord_counts)

                assign_props(f_base, feature["properties"])
                # update list of all properties
                for prop in feature["properties"]:
                    if prop not in all_props:
                        all_props.append(prop)

                assign_display_properties(feature, f_base,  obj_get_color)
                data["features"].append(feature)
        
        assign_missing_props(data["features"], all_props)

        if len(data["features"])==0:
            raise ValueError("No supported features found")
        
        time2 = datetime.now()
        print(f"Loading features before reprojecting time: {(time2-time1).total_seconds()}")

        reproject_bulk(self, all_coords, all_coord_counts, [f["geometry"] for f in data["features"]])

        return data
    
    def assign_coordinate_system_to_geojson(self, data: Dict):

        crs = {
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            }
        }

        data["crs"] = crs

    def get_python_path(self):
        if sys.platform.startswith("linux"):
            return sys.executable
        pythonExec = os.path.dirname(sys.executable)
        if sys.platform == "win32":
            pythonExec += "\\python"
        else:
            pythonExec += "/bin/python3"
        return pythonExec
