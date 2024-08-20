
from typing import Dict, List, Tuple

DEFAULT_COLOR = (255 << 24) + (150 << 16) + (150 << 8) + 150

def find_display_obj(obj) -> Tuple["Base", "Base"]:
    """Get displayable object."""

    from specklepy.objects.geometry import Base, Mesh

    displayVal = obj
    displayValForColor = obj

    if hasattr(obj, 'displayValue'):
        displayValForColor = getattr(obj, 'displayValue')
    elif hasattr(obj, '@displayValue'):
        displayValForColor = getattr(obj, '@displayValue')

    if isinstance(displayValForColor, List):
        faces = []
        verts = []
        colors = []
        for item in displayValForColor:
            if isinstance(item, Mesh):
                start_vert_count = int(len(verts)/3)

                # only add colors if existing and incoming colors are valid (same length as vertices)
                if len(colors) == start_vert_count and isinstance(item.colors, List) and len(item.colors)== int(len(item.vertices)/3)>0:
                    colors.extend(item.colors)
                else:
                    colors = []

                verts.extend(item.vertices)

                count = 0
                for _ in item.faces:
                    try:
                        vert_num = item.faces[count]
                        faces.append(vert_num)
                        faces.extend([ x+start_vert_count for x in item.faces[count+1 : count+1+vert_num]])
                        count += vert_num+1
                    except IndexError:
                        break
            elif item is not None:
                displayValForColor = item

        mesh = Mesh.create(faces= faces, vertices=verts, colors=colors)
        for prop in displayValForColor[0].get_member_names():
            if prop not in ["colors", "vertices", "faces"]:
                mesh[prop] = getattr(displayValForColor[0], prop)
        displayValForColor = mesh
    
    displayVal = displayValForColor

    # if not searching for colored object, return GisFeatures as is
    if obj.speckle_type.endswith(".GisFeature"):
        displayVal = obj

    return displayVal, displayValForColor

def get_display_units(context_list: List["TraversalContext"]) -> None | str:
    """Get units from either of displayable objects."""

    from specklepy.objects.geometry import Base

    displayUnits = None

    for item in context_list:
        if hasattr(item.current, "displayValue"):
            try:
                displayVal = item.current["displayValue"]
            except:
                displayVal = item.current.displayValue
            if isinstance(displayVal, list) and len(displayVal)>0:
                displayUnits = displayVal[0].units
                break
            elif isinstance(displayVal, Base):
                displayUnits = item.current.units
                break
        else:
            if item.current.units is not None:
                displayUnits = item.current.units
                break

    return displayUnits

def set_default_color(context_list: List["TraversalContext"]) -> None:
    """Get and set the default color."""

    from specklepy.objects.GIS.layers import VectorLayer

    global DEFAULT_COLOR
    DEFAULT_COLOR = (255 << 24) + (150 << 16) + (150 << 8) + 150

    for item in context_list:
        # for GIS-commits, use default blue color
        if isinstance(item.current, VectorLayer):
            DEFAULT_COLOR = (255 << 24) + (10 << 16) + (132 << 8) + 255
            break

def assign_color(obj_display, props) -> None:
    """Get and assign color to feature displayProperties."""

    from specklepy.objects.geometry import Mesh

    # initialize Speckle Blue color
    color = DEFAULT_COLOR

    try:
        if hasattr(obj_display, 'renderMaterial'):
            color = obj_display['renderMaterial']['diffuse']
        elif hasattr(obj_display, '@renderMaterial'):
            color = obj_display['@renderMaterial']['diffuse']
        elif hasattr(obj_display, 'displayStyle'):
            color = obj_display['displayStyle']['color']
        elif hasattr(obj_display, '@displayStyle'):
            color = obj_display['@displayStyle']['color']
        elif isinstance(obj_display, Mesh) and isinstance(obj_display.colors, List):
            sameColors = True
            color1 = obj_display.colors[0]
            for c in obj_display.colors:
                if c != color1:
                    sameColors = False
                    break
            if sameColors is True:
                color = color1
    except Exception as e:
        print(e)
    
    r, g, b = get_r_g_b(color)
    hex_color = '#%02x%02x%02x' % (r, g, b)
    props['color'] = hex_color

def get_r_g_b(rgb: int) -> Tuple[int, int, int]:
    """Get R, G, B values from int."""

    r = g = b = 0
    try:
        r = (rgb & 0xFF0000) >> 16
        g = (rgb & 0xFF00) >> 8
        b = rgb & 0xFF
    except Exception as e:
        r = g = b = 150
    return r, g, b

def assign_display_properties(feature: Dict, f_base: "Base",  obj_display: "Base") -> None:
    """Assign displayProperties to the feature."""
    
    from specklepy.objects.geometry import Mesh, Brep    

    feature["displayProperties"] = {}
    assign_color(obj_display, feature["displayProperties"])

    # other properties for rendering 
    if isinstance(f_base, Mesh) or isinstance(f_base, Brep):
        feature["displayProperties"]['lineWidth'] = 0.3
    elif "Line" in feature["geometry"]["type"]: 
        feature["displayProperties"]['lineWidth'] = 3
    else: 
        feature["displayProperties"]['lineWidth'] = 1

    # if "Point" in feature["geometry"]["type"]:
    try:
        feature["displayProperties"]["radius"] = feature["properties"]["weight"]
    except:
        feature["displayProperties"]["radius"] = 10
