
from datetime import datetime
from typing import Dict, List


def initialize_features(all_coords, all_coord_counts, data, context_list, comments: Dict) -> None:
    """Create features with props and displayProps, and assign flat list of coordinates."""

    from pygeoapi.provider.speckle_utils.props_utils import assign_props, assign_missing_props
    from pygeoapi.provider.speckle_utils.converter_utils import assign_geometry
    from pygeoapi.provider.speckle_utils.display_utils import find_display_obj, assign_display_properties

    print(f"Creating features..")
    time1 = datetime.now()
    
    all_props = []

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
        try: # don't break the code if 1 feature fails
            coords = []
            coord_counts = []
            obj_display, obj_get_color = find_display_obj(f_base)
            coords, coord_counts = assign_geometry(feature, obj_display)
        except Exception as e:
            print(e)
            pass

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

    ####################### create comment features
    for comm_id, comment in comments.items():
        # initialize comment
        feature: Dict = {
            "type": "Feature",
            "id": comm_id,
            "geometry": {},
            "properties": {
                "text": "",
                "urls": []
            },
        }

        try: # don't break the code if 1 comment fails
            coords = []
            coord_counts = []
            coords, coord_counts = assign_geometry(feature, comment["position"])
        except Exception as e:
            print(e)
            pass

        if len(coords)!=0:
            all_coords.extend(coords)
            all_coord_counts.append(coord_counts)
            assign_comment_data(comment["items"], feature["properties"])
            print(feature["properties"]["text"])
            data["comments"].append(feature)
    ########################

    if len(data["features"])==0:
        raise ValueError("No supported features found")
    
    time2 = datetime.now()
    print(f"Creating features time: {(time2-time1).total_seconds()}")

def assign_comment_data(comments, properties):

    for item in comments:
        r'''
        "author": author_name,
        "date": created_date, # e.g. 2024-08-25T13:52:50.562Z
        "text": raw_text,
        "attachments": attachments_paths,
        '''
        try:
            formatted_time = datetime.strptime(item["date"].replace("T", " ").replace("Z","").split(".")[0], '%Y-%m-%d %H:%M:%S')
        except:
            formatted_time = item["date"]
        
        properties["text"] += f"<b>{item["author"]}</b> at {formatted_time}: <br> &emsp; {item["text"]}<br><br>"
        properties["urls"].append("attachments")

        #properties["author"] = comment["author"]
        #properties["date"] = comment["date"]
        #properties["text"] = comment["text"]
        #properties["attachments"] = comment["attachments"]



def create_features(self: "SpeckleProvider", context_list: List["TraversalContext"], comments: Dict, data: Dict) -> None:
    """Create features from the list of traversal context."""

    from pygeoapi.provider.speckle_utils.coords_utils import reproject_bulk

    all_coords = []
    all_coord_counts = []
    initialize_features(all_coords, all_coord_counts, data, context_list, comments)
    all_features = data["features"] + data["comments"]
    reproject_bulk(self, all_coords, all_coord_counts, [f["geometry"] for f in all_features])
