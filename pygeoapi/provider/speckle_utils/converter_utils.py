
from typing import Dict, List


def assign_geometry(feature: Dict, f_base) -> ( List[List[List[float]]], List[List[None| List[int]]] ):
    """Assign geom type and convert object coords into flat lists of coordinates and schema."""

    from specklepy.objects.geometry import Point, Line, Polyline, Curve, Mesh, Brep
    from specklepy.objects.GIS.geometry import GisPolygonGeometry
    from specklepy.objects.GIS.GisFeature import GisFeature

    geometry = feature["geometry"]
    coords = [] 
    coord_counts = []

    if isinstance(f_base, Point):
        geometry["type"] = "MultiPoint"
        coord_counts.append(None)

        coords.append([f_base.x, f_base.y])
        coord_counts.append([1])

    elif isinstance(f_base, Mesh) or isinstance(f_base, Brep):
        geometry["type"] = "MultiPolygon"
        coord_counts.append(None) # as an indicator of a MultiPolygon

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

        count: int = 0
        for i, pt_count in enumerate(faces):
            if i != count:
                continue

            # old encoding
            if pt_count == 0:
                pt_count = 3
            elif pt_count == 1:
                pt_count = 4
            coord_counts.append([pt_count])

            for vertex_index in faces[count + 1 : count + 1 + pt_count]:
                x = vertices[vertex_index * 3]
                y = vertices[vertex_index * 3 + 1]
                coords.append([x, y])

            count += pt_count + 1

    elif f_base.speckle_type.endswith(".GisFeature") and len(f_base["geometry"]) > 0: # isinstance(f_base, GisFeature) and len(f_base.geometry) > 0:
        # GisFeature doesn't deserialize properly, need to check for speckle_type 

        if isinstance(f_base.geometry[0], Point):
            geometry["type"] = "MultiPoint"
            coord_counts.append(None)
            
            for geom in f_base.geometry:
                coords.append([geom.x, geom.y])
                coord_counts.append([1])
            
        elif isinstance(f_base.geometry[0], Polyline):
            geometry["type"] = "MultiLineString"
            coord_counts.append(None)

            for geom in f_base.geometry:
                coord_counts.append([])
                local_poly_count = 0

                for pt in geom.as_points():
                    coords.append([pt.x, pt.y])
                    local_poly_count += 1
                if len(coords)>2 and geom.closed is True and coords[0] != coords[-1]:
                    coords.append(coords[0])
                    local_poly_count += 1

                coord_counts[-1].append(local_poly_count)

        elif isinstance(f_base.geometry[0], GisPolygonGeometry):
            geometry["type"] = "MultiPolygon"
            coord_counts.append(None)

            for polygon in f_base.geometry:
                coord_counts.append([])
                boundary_count = 0
                for pt in polygon.boundary.as_points():
                    coords.append([pt.x, pt.y])
                    boundary_count += 1
                
                coord_counts[-1].append(boundary_count)

                for void in polygon.voids:
                    void_count = 0
                    for pt_void in void.as_points():
                        coords.append([pt_void.x, pt_void.y])
                        void_count += 1
                    
                    coord_counts[-1].append(void_count)

    elif isinstance(f_base, Line):
        geometry["type"] = "LineString"
        start = [f_base.start.x, f_base.start.y]
        end = [f_base.end.x, f_base.end.y]
        
        coords.extend([start, end])
        coord_counts.append([2])

    elif isinstance(f_base, Polyline):
        geometry["type"] = "LineString"
        for pt in f_base.as_points():
            coords.append([pt.x, pt.y])
        if len(coords)>2 and f_base.closed is True and coords[0] != coords[-1]:
            coords.append(coords[0])
            
        coord_counts.append([len(coords)])

    elif isinstance(f_base, Curve):
        geometry["type"] = "LineString"
        for pt in f_base.displayValue.as_points():
            coords.append([pt.x, pt.y])
        if len(coords)>2 and f_base.displayValue.closed is True and coords[0] != coords[-1]:
            coords.append(coords[0])

        coord_counts.append([len(coords)])

    else:
        geometry = {}
        # print(f"Unsupported geometry type: {f_base.speckle_type}")
    
    return coords, coord_counts
