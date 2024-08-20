
def create_crs_from_wkt(self: "SpeckleProvider", wkt: str | None) -> None:
    """Create and assign CRS object from WKT string."""

    from pyproj import CRS
    self.crs = CRS.from_user_input(wkt)


def create_crs_from_authid(self: "SpeckleProvider", authid: str | None) -> None:
    """Create and assign CRS object from Authority ID."""

    from pyproj import CRS

    crs_obj = CRS.from_string(authid)
    self.crs = crs_obj

    
def create_crs_default(self: "SpeckleProvider") -> None:
    """Create and assign custom CRS using SpeckleProvider Lat & Lon."""

    from pyproj import CRS

    wkt = f'PROJCS["SpeckleCRS_latlon_{self.lat}_{self.lon}", GEOGCS["GCS_WGS_1984", DATUM["D_WGS_1984", SPHEROID["WGS_1984", 6378137.0, 298.257223563]], PRIMEM["Greenwich", 0.0], UNIT["Degree", 0.0174532925199433]], PROJECTION["Transverse_Mercator"], PARAMETER["False_Easting", 0.0], PARAMETER["False_Northing", 0.0], PARAMETER["Central_Meridian", {self.lon}], PARAMETER["Scale_Factor", 1.0], PARAMETER["Latitude_Of_Origin", {self.lat}], UNIT["Meter", 1.0]]'
    crs_obj = CRS.from_user_input(wkt)
    self.crs = crs_obj
    
def create_crs_dict(self: "SpeckleProvider", offset_x, offset_y, displayUnits: str | None) -> None:
    """Create and assign CRS object from WKT string."""

    if self.crs is not None:
        self.crs_dict = {
            "wkt": self.crs.to_wkt(),
            "offset_x": offset_x,
            "offset_y": offset_y,
            "rotation": self.north_degrees,
            "units_native": displayUnits,
            "obj": self.crs,
        }

