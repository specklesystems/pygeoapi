import sys 
from pathlib import Path
import shutil

def get_specklepy_path():
    root_path = Path(sys.executable).parent.parent
    credentials_path = Path(root_path, "Lib", "site-packages", "specklepy")

    return credentials_path

def get_credentials_path():
    specklepy_path = get_specklepy_path()
    credentials_path = Path(specklepy_path, "core", "api", "credentials.py")

    return str(credentials_path)

def get_gis_feature_path_src():
    specklepy_path = Path(sys.executable).parent.parent
    credentials_path = Path(specklepy_path, "pygeoapi", "pygeoapi", "provider", "speckle_utils", "GisFeature.py")

    return str(credentials_path)

def get_gis_feature_path_dst():
    specklepy_path = get_specklepy_path()
    credentials_path = Path(specklepy_path, "objects", "GIS", "GisFeature.py")

    return str(credentials_path)

def patch_credentials():
    """Patches the installer with the correct connector version and specklepy version"""
    
    file_path = get_credentials_path()

    with open(file_path, "r") as file:
        lines = file.readlines()
        new_lines = []
        for i, line in enumerate(lines):
            if "Account.model_validate_json" in line:
                line = line.replace("Account.model_validate_json", "Account.parse_raw")
            new_lines.append(line)
    file.close()

    with open(file_path, "w") as file:
        file.writelines(new_lines)
    file.close()
    
def copy_gis_feature():
    shutil.copyfile(get_gis_feature_path_src(), get_gis_feature_path_dst())
