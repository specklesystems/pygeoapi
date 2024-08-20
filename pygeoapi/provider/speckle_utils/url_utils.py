

from typing import Dict


def get_set_url_parameters(self: "SpeckleProvider"):

    from pygeoapi.provider.speckle_utils.crs_utils import create_crs_from_authid

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

        # if CRS parameter present, create and assign CRS:
        if len(crs_authid)>3:
            create_crs_from_authid(self)
