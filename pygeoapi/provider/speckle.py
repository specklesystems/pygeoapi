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

import copy
import json
import logging
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from pygeoapi.provider.base import BaseProvider, ProviderItemNotFoundError
from pygeoapi.util import crs_transform


LOGGER = logging.getLogger(__name__)
_user_data_env_var = "SPECKLE_USERDATA_PATH"
_application_name = "Speckle"
_host_application = "pygeoapi"


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
            #    "Please provide Speckle project link as an argument, e.g.: 'http://localhost:5000/?limit=100000&https://app.speckle.systems/projects/55a29f3e9d/models/f5e6de9149'"
            # )

        from subprocess import run

        path = str(self.connector_installation_path(_host_application))

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
                    "specklepy==2.19.5",
                    "-t",
                    str(path),
                ],
                capture_output=True,
            )

            if completed_process.returncode != 0:
                m = f"Failed to install dependenices through pip, got {completed_process.returncode} as return code. Full log: {completed_process}"
                print(m)
                print(completed_process.stdout)
                print(completed_process.stderr)
                raise Exception(m)

        # TODO: replace 1 line in specklepy
        
        # assign global values
        self.url: str = self.data # to store the value and check if self.data has changed

        self.speckle_data = None

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

        if self.data == "":
            raise ValueError(
                "Please provide Speckle project link as an argument, e.g.: http://localhost:5000/?limit=100000&speckleUrl=https://app.speckle.systems/projects/55a29f3e9d/models/f5e6de9149"
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
                    self.lat = float(item.split("lat=")[1])
                elif "lon=" in item:
                    self.lon = float(item.split("lon=")[1])
                elif "northdegrees=" in item:
                    self.north_degrees = float(item.split("northdegrees=")[1])

            # if CRS assigned, create one:
            if len(crs_authid)>3:
                self.create_crs_from_authid()

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
        from specklepy.core.api import operations
        from specklepy.core.api.wrapper import StreamWrapper
        from specklepy.core.api.client import SpeckleClient

        url: str = self.url.lower().split("speckleurl=")[-1].split("&")[0]
        
        # get URL that will not trigget Client init
        url_fe1: str = url.replace("projects", "streams").split("models")[0]
        wrapper: StreamWrapper = StreamWrapper(url_fe1)

        # set actual branch
        wrapper.model_id = url.split("models/")[1].split("/")[0].split("&")[0].split("@")[0].split("?")[0]
        
        # get client by URL, no authentication
        client = SpeckleClient(host=wrapper.host, use_ssl=wrapper.host.startswith("https"))

        # get branch data
        branch = client.branch.get(
            stream_id =wrapper.stream_id, name=wrapper.model_id
        )

        commit = branch["commits"]["items"][0]
        objId = commit["referencedObject"]

        transport = self.validateTransport(client, wrapper.stream_id)
        if transport == None:
            raise SpeckleException("Transport not found")

        # data transfer
        try:
            commit_obj = operations.receive(objId, transport, None)
        except SpeckleException as ex:
            # e.g. SpeckleException: Can't get object b53a53697a/f8ce82b242e05eeaab4c6c59fb25e4a0: HTTP error 404 ()
            raise SpeckleException("Fetching data failed, Project might be set to Private.")

        client.commit.received(
            wrapper.stream_id,
            commit["id"],
            source_application="pygeoapi",
            message="Received commit in pygeoapi",
        )
        print(f"Rendering model '{branch['name']}'")
        return self.traverse_data(commit_obj)

    def traverse_data(self, commit_obj):

        from specklepy.objects.geometry import Point, Line, Polyline, Curve, Mesh, Brep
        from specklepy.objects.GIS.geometry import GisPolygonElement
        from specklepy.objects.graph_traversal.traversal import (
            GraphTraversal,
            TraversalRule,
        )

        supported_types = [GisPolygonElement, Mesh, Brep, Point, Line, Polyline, Curve]
        # traverse commit
        data: Dict[str, Any] = {
            "type": "FeatureCollection",
            "features": [],
        }
        self.assign_crs_to_geojson(data)

        rule = TraversalRule(
            [lambda _: True],
            lambda x: [
                item
                for item in x.get_member_names()
                if isinstance(getattr(x, item, None), list)
                and type(x) not in supported_types
            ],
        )
        context_list = [x for x in GraphTraversal([rule]).traverse(commit_obj)]

        # iterate Speckle objects to get "crs" property
        crs = None
        displayUnits = None
        for item in context_list:
            if (
                crs is None
                and item.current.speckle_type.endswith("Layer")
                and hasattr(item.current, "crs")
            ):
                crs = item.current["crs"]
                displayUnits = crs["units_native"]
                self.create_crs_from_wkt(crs["wkt"])
                break
            elif displayUnits is None and type(item.current) in supported_types:
                displayUnits = item.current.units

        if self.crs is None:
            self.create_crs_default()

        self.create_crs_dict(displayUnits)

        # iterate to get features
        list_len = len(context_list)

        load = 0
        print(f"{load}% loaded")

        for i, item in enumerate(context_list):
            new_load = round(i / list_len * 10, 1) * 10

            if new_load % 10 == 0 and new_load != load:
                load = round(i / list_len * 100)
                print(f"{load}% loaded")

            f_base = item.current
            f_id = item.current.id

            # feature
            feature: Dict = {
                "type": "Feature",
                # "bbox": [-180.0, -90.0, 180.0, 90.0],
                "geometry": {},
                "properties": {
                    "fid": len(data["features"]),
                    "id": f_id,
                },
            }

            # feature geometry
            self.assign_geometry(feature, f_base)
            if feature["geometry"] != {}:
                self.assign_props(f_base, feature["properties"])

                # sort by type here:
                if feature["geometry"]["type"] == "MultiPolygon":
                    data["features"].append(feature)

        return data

    def create_crs_from_wkt(self, wkt: str | None):

        from pyproj import CRS
        self.crs = CRS.from_user_input(wkt)

    def create_crs_from_authid(self, authid: str | None):

        from pyproj import CRS

        crs_obj = CRS.from_string(authid)
        self.crs = crs_obj

    def create_crs_default(self):

        from pyproj import CRS

        wkt = f'PROJCS["SpeckleCRS_latlon_{self.lat}_{self.lon}", GEOGCS["GCS_WGS_1984", DATUM["D_WGS_1984", SPHEROID["WGS_1984", 6378137.0, 298.257223563]], PRIMEM["Greenwich", 0.0], UNIT["Degree", 0.0174532925199433]], PROJECTION["Transverse_Mercator"], PARAMETER["False_Easting", 0.0], PARAMETER["False_Northing", 0.0], PARAMETER["Central_Meridian", {self.lon}], PARAMETER["Scale_Factor", 1.0], PARAMETER["Latitude_Of_Origin", {self.lat}], UNIT["Meter", 1.0]]'
        crs_obj = CRS.from_user_input(wkt)
        self.crs = crs_obj

    def create_crs_dict(self, displayUnits: str | None):
        if self.crs is not None:
            self.crs_dict = {
                "wkt": self.crs.to_wkt(),
                "offset_x": 0,
                "offset_y": 0,
                "rotation": self.north_degrees,
                "units_native": displayUnits,
                "obj": self.crs,
            }


    def assign_geometry(self, feature: Dict, f_base):

        from specklepy.objects.geometry import Point, Line, Polyline, Curve, Mesh, Brep
        from specklepy.objects.GIS.geometry import GisPolygonElement

        geometry = feature["geometry"]

        if isinstance(f_base, Point):
            geometry["type"] = "Point"
            geometry["coordinates"] = self.reproject_2d_coords_list(
                [[f_base.x, f_base.y]]
            )[0]

        elif isinstance(f_base, Mesh) or isinstance(f_base, Brep):
            faces = []
            vertices = []
            if isinstance(f_base, Mesh):
                faces = f_base.faces
                vertices = f_base.vertices
            elif isinstance(f_base, Brep):
                if f_base.displayValue is None or (
                    isinstance(f_base.displayValue, list)
                    and len(f_base.displayValue) == 0
                ):
                    geometry = {}
                    return
                elif isinstance(f_base.displayValue, list):
                    faces = f_base.displayValue[0].faces
                    vertices = f_base.displayValue[0].vertices
                else:
                    faces = f_base.displayValue.faces
                    vertices = f_base.displayValue.vertices

            geometry["type"] = "MultiPolygon"
            geometry["coordinates"] = []

            count: int = 0
            all_face_counts = []
            flat_boundaries_list = []
            for i, pt_count in enumerate(faces):
                if i != count:
                    continue

                # old encoding
                if pt_count == 0:
                    pt_count = 3
                elif pt_count == 1:
                    pt_count = 4
                all_face_counts.append(pt_count)

                new_poly = []
                boundary = []

                for vertex_index in faces[count + 1 : count + 1 + pt_count]:
                    x = vertices[vertex_index * 3]
                    y = vertices[vertex_index * 3 + 1]
                    flat_boundaries_list.append([x, y])

                new_poly.append(boundary)
                geometry["coordinates"].append(new_poly)
                count += pt_count + 1

            flat_boundaries_list_reprojected = self.reproject_2d_coords_list(
                flat_boundaries_list
            )
            for i, face_c in enumerate(all_face_counts):
                geometry["coordinates"][i] = [flat_boundaries_list_reprojected[:face_c]]
                flat_boundaries_list_reprojected = flat_boundaries_list_reprojected[
                    face_c:
                ]

        elif isinstance(f_base, GisPolygonElement):
            geometry["type"] = "MultiPolygon"
            geometry["coordinates"] = []

            for polygon in f_base.geometry:
                new_poly = []
                boundary = []
                for pt in polygon.boundary.as_points():
                    boundary.append([pt.x, pt.y])
                boundary = self.reproject_2d_coords_list(boundary)
                new_poly.append(boundary)

                for void in polygon.voids:
                    new_void = []
                    for pt_void in void.as_points():
                        new_void.append([pt_void.x, pt_void.y])
                    new_void = self.reproject_2d_coords_list(new_void)
                    new_poly.append(new_void)
                geometry["coordinates"].append(new_poly)

        elif isinstance(f_base, Line):
            geometry["type"] = "LineString"
            start = [f_base.start.x, f_base.start.y]
            end = [f_base.end.x, f_base.end.y]
            geometry["coordinates"] = [start, end]
            geometry["coordinates"] = self.reproject_2d_coords_list(
                geometry["coordinates"]
            )

        elif isinstance(f_base, Polyline):
            geometry["type"] = "LineString"
            geometry["coordinates"] = []
            for pt in f_base.as_points():
                geometry["coordinates"].append([pt.x, pt.y])
            geometry["coordinates"] = self.reproject_2d_coords_list(
                geometry["coordinates"]
            )
        elif isinstance(f_base, Curve):
            geometry["type"] = "LineString"
            geometry["coordinates"] = []
            for pt in f_base.displayValue.as_points():
                geometry["coordinates"].append([pt.x, pt.y])
            geometry["coordinates"] = self.reproject_2d_coords_list(
                geometry["coordinates"]
            )
        else:
            geometry = {}
            # print(f"Unsupported geometry type: {f_base.speckle_type}")

    def reproject_2d_coords_list(self, coords_in: List[list]):

        from pyproj import Transformer
        from pyproj import CRS

        coords_offset = self.offset_rotate(copy.deepcopy(coords_in))

        transformer = Transformer.from_crs(
            self.crs,
            CRS.from_user_input(4326),
            always_xy=True,
        )
        return [[pt[0], pt[1]] for pt in transformer.itransform(coords_offset)]

    def offset_rotate(self, coords_in: List[list]):

        from specklepy.objects.units import get_scale_factor_from_string

        scale_factor = 1
        if isinstance(self.crs_dict["units_native"], str):
            scale_factor = get_scale_factor_from_string(self.crs_dict["units_native"], "m")

        final_coords = []
        for coord in coords_in:
            a = self.crs_dict["rotation"] * math.pi / 180
            x2 = coord[0] * math.cos(a) - coord[1] * math.sin(a)
            y2 = coord[0] * math.sin(a) + coord[1] * math.cos(a)
            final_coords.append(
                [
                    scale_factor * (x2 + self.crs_dict["offset_x"]),
                    scale_factor * (y2 + self.crs_dict["offset_y"]),
                ]
            )

        return final_coords

    def assign_crs_to_geojson(self, data: Dict):

        crs = {
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            }
        }

        data["crs"] = crs

    def assign_props(self, obj, props):
        from specklepy.objects.geometry import Base

        for prop_name in obj.get_member_names():
            value = getattr(obj, prop_name)
            if (
                prop_name
                in [
                    "geometry",
                    "units",
                    "totalChildrenCount",
                    "vertices",
                    "faces",
                    "displayValue",
                    "displayStyle",
                    "textureCoordinates",
                    "renderMaterial",
                ]
                # or prop_name.lower() == "id"
            ):
                pass
            elif isinstance(value, Base) and prop_name == "attributes":
                self.assign_props(value, props)
            elif (
                isinstance(value, Base)
                or isinstance(value, List)
                or isinstance(value, Dict)
            ):
                props[prop_name] = str(value)
            else:
                props[prop_name] = value

    def tryGetStream(
        self,
        sw: "StreamWrapper",
        client: "SpeckleClient"
    ) -> Union["Stream", None]:

        from specklepy.logging.exceptions import SpeckleException
        from specklepy.core.api.client import SpeckleClient
        from specklepy.core.api.models import Stream

        stream = client.stream.get(
            id=sw.stream_id, branch_limit=100, commit_limit=100
        )
        if isinstance(stream, Stream) or isinstance(stream, Dict):
            # try get stream, only read access needed
            return stream
        else:
            raise SpeckleException(f"Fetching Speckle Project failed: {stream}. Project might be private.")


    def validateTransport(
        self, client: "SpeckleClient", streamId: str
    ) -> Union["ServerTransport", None]:

        from specklepy.core.api.credentials import (
            get_default_account,
        )
        from specklepy.transports.server import ServerTransport

        account = client.account
        if not account.token:
            account = get_default_account()
        transport = ServerTransport(client=client, account=account, stream_id=streamId)
        return transport

    def get_python_path(self):
        if sys.platform.startswith("linux"):
            return sys.executable
        pythonExec = os.path.dirname(sys.executable)
        if sys.platform == "win32":
            pythonExec += "\\python"
        else:
            pythonExec += "/bin/python3"
        return pythonExec

    def user_application_data_path(self) -> "Path":
        """Get the platform specific user configuration folder path"""
        from pathlib import Path

        path_override = self._path()
        if path_override:
            return path_override

        try:
            if sys.platform.startswith("win"):
                app_data_path = os.getenv("APPDATA")
                if not app_data_path:
                    raise Exception("Cannot get appdata path from environment.")
                return Path(app_data_path)
            else:
                # try getting the standard XDG_DATA_HOME value
                # as that is used as an override
                app_data_path = os.getenv("XDG_DATA_HOME")
                if app_data_path:
                    return Path(app_data_path)
                else:
                    return self.ensure_folder_exists(Path.home(), ".config")
        except Exception as ex:
            raise Exception("Failed to initialize user application data path.", ex)

    def ensure_folder_exists(self, base_path: "Path", folder_name: str) -> "Path":
        from pathlib import Path

        path = base_path.joinpath(folder_name)
        path.mkdir(exist_ok=True, parents=True)
        return path

    def _path(self) -> Optional["Path"]:
        from pathlib import Path

        """Read the user data path override setting."""
        path_override = os.environ.get(_user_data_env_var)
        if path_override:
            return Path(path_override)
        return None

    def connector_installation_path(self, host_application: str) -> "Path":
        connector_installation_path = self.user_speckle_connector_installation_path(
            host_application
        )
        connector_installation_path.mkdir(exist_ok=True, parents=True)

        # set user modules path at beginning of paths for earlier hit
        if sys.path[0] != connector_installation_path:
            sys.path.insert(0, str(connector_installation_path))

        # print(f"Using connector installation path {connector_installation_path}")
        return connector_installation_path

    def user_speckle_connector_installation_path(self, host_application: str) -> "Path":
        """
        Gets a connector specific installation folder.
        In this folder we can put our connector installation and all python packages.
        """
        return self.ensure_folder_exists(
            self.ensure_folder_exists(
                self.user_speckle_folder_path(), "connector_installations"
            ),
            host_application,
        )

    def user_speckle_folder_path(self) -> "Path":
        """Get the folder where the user's Speckle data should be stored."""
        return self.ensure_folder_exists(
            self.user_application_data_path(), _application_name
        )
