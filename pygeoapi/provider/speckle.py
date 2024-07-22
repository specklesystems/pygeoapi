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

        self.speckle_data = None
        self.url = self.data.split("&")[0]
        self.lat = 51.52486388756923
        self.lon = 0.1621445437168942
        self.north_degrees = 0

    def get_fields(self):
        """
         Get provider field information (names, types)
        :returns: dict of fields
        """

        fields = {}
        LOGGER.debug("Treating all columns as string types")

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

        if (
            isinstance(self.data, str)
            and "projects" in self.data
            and "models" in self.data
        ):
            request_str = self.data.split("?")[-1]
            for item in request_str.split("&"):
                if "https://" in item:
                    self.url = item
                elif "lat=" in item:
                    self.lat = float(item.split("lat=")[1])
                elif "lon=" in item:
                    self.lon = float(item.split("lon=")[1])
                elif "northDegrees=" in item:
                    self.north_degrees = float(item.split("northDegrees=")[1])

        # check if it's a new request (self.data was updated)
        new_request = True
        new_url = ""
        new_lat = new_lon = new_north = 0

        for item in self.data.split("&"):
            if "https://" in item:
                new_url = item
            elif "lat=" in item:
                new_lat = float(item.split("lat=")[1])
            elif "lon=" in item:
                new_lon = float(item.split("lon=")[1])
            elif "northDegrees=" in item:
                new_north = float(item.split("northDegrees=")[1])
        if (
            new_url == self.url
            and new_lat == self.lat
            and new_lon == self.lon
            and new_north == self.north_degrees
        ):
            new_request = False

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

        data = self.speckle_data

        # filter by properties if set
        if properties:
            data["features"] = [
                f
                for f in data["features"]
                if all([str(f["properties"][p[0]]) == str(p[1]) for p in properties])
            ]  # noqa

        # All features must have ids, TODO must be unique strings
        if isinstance(data, str):
            raise Exception(data)
        for i in data["features"]:
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
        return data

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

        all_data = self._load()

        if (
            self.id_field not in new_feature
            and self.id_field not in new_feature["properties"]
        ):
            new_feature["properties"][self.id_field] = str(uuid.uuid4())

        all_data["features"].append(new_feature)

        with open(self.data, "w") as dst:
            dst.write(json.dumps(all_data))

    def update(self, identifier, new_feature):
        """Updates an existing feature id with new_feature
        :param identifier: feature id
        :param new_feature: new GeoJSON feature dictionary
        """

        all_data = self._load()
        for i, feature in enumerate(all_data["features"]):
            if self.id_field in feature:
                if feature[self.id_field] == identifier:
                    new_feature["properties"][self.id_field] = identifier
                    all_data["features"][i] = new_feature
            elif self.id_field in feature["properties"]:
                if feature["properties"][self.id_field] == identifier:
                    new_feature["properties"][self.id_field] = identifier
                    all_data["features"][i] = new_feature
        with open(self.data, "w") as dst:
            dst.write(json.dumps(all_data))

    def delete(self, identifier):
        """Deletes an existing feature
        :param identifier: feature id
        """

        all_data = self._load()
        for i, feature in enumerate(all_data["features"]):
            if self.id_field in feature:
                if feature[self.id_field] == identifier:
                    all_data["features"].pop(i)
            elif self.id_field in feature["properties"]:
                if feature["properties"][self.id_field] == identifier:
                    all_data["features"].pop(i)
        with open(self.data, "w") as dst:
            dst.write(json.dumps(all_data))

    def __repr__(self):
        return f"<SpeckleProvider> {self.data}"

    def load_speckle_data(self: str):

        from specklepy.logging.exceptions import SpeckleException
        from specklepy.core.api import operations
        from specklepy.core.api.wrapper import StreamWrapper

        wrapper: StreamWrapper = StreamWrapper(self.url.split("&")[0])
        client, stream = self.tryGetClient(wrapper)
        stream = self.validateStream(stream)
        branchName = wrapper.branch_name
        if branchName is None:
            branchName = "main"

        if wrapper.commit_id == None:
            stream = client.stream.get(
                id=stream["id"], branch_limit=100, commit_limit=100
            )

        branch = self.validateBranch(stream, branchName)
        commitId = wrapper.commit_id
        commit = self.validateCommit(branch, commitId)
        objId = commit["referencedObject"]

        if branch["name"] is None or commit["id"] is None or objId is None:
            raise SpeckleException("Something went wrong")

        transport = self.validateTransport(client, wrapper.stream_id)
        if transport == None:
            raise SpeckleException("Transport not found")

        # data transfer
        commit_obj = operations.receive(objId, transport, None)
        client.commit.received(
            wrapper.stream_id,
            commit["id"],
            source_application="pygeoapi",
            message="Received commit in pygeoapi",
        )
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
        self.assign_crs(data)

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

        # iterate to get CRS
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
                break
            elif displayUnits is None and type(item.current) in supported_types:
                displayUnits = item.current.units

        # if crs not found, generate one
        if crs is None:
            wkt = f'PROJCS["SpeckleCRS_latlon_{self.lat}_{self.lon}", GEOGCS["GCS_WGS_1984", DATUM["D_WGS_1984", SPHEROID["WGS_1984", 6378137.0, 298.257223563]], PRIMEM["Greenwich", 0.0], UNIT["Degree", 0.0174532925199433]], PROJECTION["Transverse_Mercator"], PARAMETER["False_Easting", 0.0], PARAMETER["False_Northing", 0.0], PARAMETER["Central_Meridian", {self.lon}], PARAMETER["Scale_Factor", 1.0], PARAMETER["Latitude_Of_Origin", {self.lat}], UNIT["Meter", 1.0]]'
            crs = {
                "wkt": wkt,
                "offset_x": 0,
                "offset_y": 0,
                "rotation": self.north_degrees,
                "units_native": displayUnits,
            }

        # iterate to get features
        list_len = len(context_list)

        load = 0
        print(f"{load}% loaded")

        for i, item in enumerate(context_list):
            new_load = round(i / list_len * 10, 1) * 10
            # if new_load >= 10:
            #    break
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
            self.assign_geometry(crs, feature, f_base)
            if feature["geometry"] != {}:
                self.assign_props(f_base, feature["properties"])

                # sort by type here:
                if feature["geometry"]["type"] == "MultiPolygon":
                    data["features"].append(feature)

        return data

    def assign_geometry(self, crs, feature: Dict, f_base):

        from specklepy.objects.geometry import Point, Line, Polyline, Curve, Mesh, Brep
        from specklepy.objects.GIS.geometry import GisPolygonElement

        geometry = feature["geometry"]

        if isinstance(f_base, Point):
            geometry["type"] = "Point"
            geometry["coordinates"] = self.reproject_2d_coords_list(
                crs, [[f_base.x, f_base.y]]
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
                crs, flat_boundaries_list
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
                boundary = self.reproject_2d_coords_list(crs, boundary)
                new_poly.append(boundary)

                for void in polygon.voids:
                    new_void = []
                    for pt_void in void.as_points():
                        new_void.append([pt_void.x, pt_void.y])
                    new_void = self.reproject_2d_coords_list(crs, new_void)
                    new_poly.append(new_void)
                geometry["coordinates"].append(new_poly)

        elif isinstance(f_base, Line):
            geometry["type"] = "LineString"
            start = [f_base.start.x, f_base.start.y]
            end = [f_base.end.x, f_base.end.y]
            geometry["coordinates"] = [start, end]
            geometry["coordinates"] = self.reproject_2d_coords_list(
                crs, geometry["coordinates"]
            )

        elif isinstance(f_base, Polyline):
            geometry["type"] = "LineString"
            geometry["coordinates"] = []
            for pt in f_base.as_points():
                geometry["coordinates"].append([pt.x, pt.y])
            geometry["coordinates"] = self.reproject_2d_coords_list(
                crs, geometry["coordinates"]
            )
        elif isinstance(f_base, Curve):
            geometry["type"] = "LineString"
            geometry["coordinates"] = []
            for pt in f_base.displayValue.as_points():
                geometry["coordinates"].append([pt.x, pt.y])
            geometry["coordinates"] = self.reproject_2d_coords_list(
                crs, geometry["coordinates"]
            )
        else:
            geometry = {}
            # print(f"Unsupported geometry type: {f_base.speckle_type}")

    def reproject_2d_coords_list(self, crs, coords_in: List[list]):

        from pyproj import Transformer
        from pyproj import CRS

        coords_offset = self.offset_rotate(crs, copy.deepcopy(coords_in))

        transformer = Transformer.from_crs(
            CRS.from_user_input(crs["wkt"]),
            CRS.from_user_input(4326),
            always_xy=True,
        )
        return [[pt[0], pt[1]] for pt in transformer.itransform(coords_offset)]

    def offset_rotate(self, crs, coords_in: List[list]):

        from specklepy.objects.units import get_scale_factor_from_string

        scale_factor = 1
        if isinstance(crs["units_native"], str):
            scale_factor = get_scale_factor_from_string(crs["units_native"], "m")

        final_coords = []
        for coord in coords_in:
            a = crs["rotation"] * math.pi / 180
            x2 = coord[0] * math.cos(a) - coord[1] * math.sin(a)
            y2 = coord[0] * math.sin(a) + coord[1] * math.cos(a)
            final_coords.append(
                [
                    scale_factor * (x2 + crs["offset_x"]),
                    scale_factor * (y2 + crs["offset_y"]),
                ]
            )

        return final_coords

    def assign_crs(self, data: Dict):

        crs = {
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            }
        }

        r"""
        crs = {
            "crs": {
                "type": "link",
                "properties": {"href": "wkt.txt", "type": "ogcwkt"},
            }
        }
        """
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

    def tryGetClient(
        self,
        sw: "StreamWrapper",
    ) -> Tuple[Union["SpeckleClient", None], Union["Stream", None]]:

        from specklepy.core.api.credentials import (
            get_local_accounts,
        )
        from specklepy.logging.exceptions import SpeckleException
        from specklepy.core.api.client import SpeckleClient
        from specklepy.core.api.models import Stream

        # only streams with write access
        client = None
        for acc in get_local_accounts():
            # only check accounts on selected server
            if acc.serverInfo.url in sw.server_url:
                client = SpeckleClient(
                    acc.serverInfo.url, acc.serverInfo.url.startswith("https")
                )
                client.authenticate_with_account(acc)
                if client.account.token is not None:
                    break

        # if token still not found
        if client is None or client.account.token is None:
            client = sw.get_client()

        if client is not None:
            stream = client.stream.get(
                id=sw.stream_id, branch_limit=100, commit_limit=100
            )
            if isinstance(stream, Stream) or isinstance(stream, Dict):
                # try get stream, only read access needed
                return client, stream
            else:
                raise SpeckleException(f"Fetching Speckle Project failed: {stream}")
        else:
            raise SpeckleException("SpeckleClient creation failed")

    def validateStream(self, stream: "Stream") -> Union["Stream", None]:

        from specklepy.logging.exceptions import SpeckleException

        if isinstance(stream, SpeckleException):
            raise stream
        if stream["branches"] is None:
            raise SpeckleException("Stream has no branches")
        return stream

    def validateBranch(
        self, stream: "Stream", branchName: str
    ) -> Union["Branch", None]:

        from specklepy.logging.exceptions import SpeckleException

        branch = None
        if not stream["branches"] or not stream["branches"]["items"]:
            return None
        for b in stream["branches"]["items"]:
            if b["name"] == branchName:
                branch = b
                break
        if branch is None:
            raise SpeckleException("Failed to find a branch")
        if branch["commits"] is None:
            raise SpeckleException("Failed to find a branch")
        if len(branch["commits"]["items"]) == 0:
            raise SpeckleException("Branch contains no commits")
        return branch

    def validateCommit(self, branch: "Branch", commitId: str) -> Union["Commit", None]:

        from specklepy.logging.exceptions import SpeckleException

        commit = None
        try:
            commitId = commitId.split(" | ")[0]
        except:
            if len(branch["commits"]["items"]) > 0:
                commit = branch["commits"]["items"][0]
            else:
                raise SpeckleException("Commit ID is not valid")

        else:
            for i in branch["commits"]["items"]:
                if i["id"] == commitId:
                    commit = i
                    break
            if commit is None:
                try:
                    commit = branch["commits"]["items"][0]
                    print("Failed to find a commit. Receiving Latest")
                except:
                    raise SpeckleException("Failed to find a commit")
        return commit

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
