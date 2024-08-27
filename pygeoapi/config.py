# =================================================================
#
# Authors: Tom Kralidis <tomkralidis@gmail.com>
#          Francesco Bartoli <xbartolone@gmail.com>
#
# Copyright (c) 2022 Tom Kralidis
# Copyright (c) 2024 Francesco Bartoli
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
import click
import json
from jsonschema import validate as jsonschema_validate
import logging
import os
import yaml

from flask import Request

from pygeoapi.util import to_json, yaml_load, THISDIR

LOGGER = logging.getLogger(__name__)
CONFIG = {}


def get_config(raw: bool = False, request: Request = None) -> dict:
    """
    Get pygeoapi configurations

    :param raw: `bool` over interpolation during config loading

    :returns: `dict` of pygeoapi configuration
    """

    if not os.environ.get("PYGEOAPI_CONFIG"):
        raise RuntimeError("PYGEOAPI_CONFIG environment variable not set")
    
    map_api_key_local = os.environ.get("MAPTILER_KEY_LOCAL")
    map_api_key_speckle = os.environ.get("MAPTILER_KEY_SPECKLE")
    
    global CONFIG

    config_file = os.environ.get("PYGEOAPI_CONFIG")
    with open(config_file, encoding="utf8") as fh:
        if raw:
            config_yaml = yaml.safe_load(fh)
        else:
            config_yaml = yaml_load(fh)

    # assign valid dictionnaries to Speckle resources
    speckle_collection_received = copy.deepcopy(config_yaml["resources"]["speckle"])

    # for the first time only: assign YAML value to CONFIG. Otherwise, don't modify
    if CONFIG == {}:
        CONFIG = config_yaml

    url_valid = False
    speckle_url = ""
    if request is not None:
        url = request.url.split("?")[-1]
        if "projects" in url and "models" in url:
            url_valid = True
            speckle_url = url

        # if a key found, replace basemap URL to MapTiler
        # make sure to restrict the usage for the key
        if ".speckle.systems" in request.url.split("?")[0] and map_api_key_speckle and len(map_api_key_speckle)>=20:
            CONFIG["server"]["map"]["url"] = r'https://api.maptiler.com/maps/dataviz/{z}/{x}/{y}.png' + f'?key={map_api_key_speckle}'
            CONFIG["server"]["map"]["attribution"] = r'<a href="https://www.maptiler.com/copyright/" target="_blank">&copy; MapTiler</a> <a href="https://www.openstreetmap.org/copyright" target="_blank">&copy; OpenStreetMap contributors</a>'

        elif map_api_key_local and len(map_api_key_local)>=20:
            CONFIG["server"]["map"]["url"] = r'https://api.maptiler.com/maps/dataviz/{z}/{x}/{y}.png' + f'?key={map_api_key_local}'
            CONFIG["server"]["map"]["attribution"] = r'<a href="https://www.maptiler.com/copyright/" target="_blank">&copy; MapTiler</a> <a href="https://www.openstreetmap.org/copyright" target="_blank">&copy; OpenStreetMap contributors</a>'
        else:
            CONFIG["server"]["map"]["url"] = r'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
            CONFIG["server"]["map"]["attribution"] = r'&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap contributors</a>'
    

    # once Speckle URL is found, set it as a provider
    if url_valid:
        # speckle_collection_pts["title"]["en"] = "Some Points"

        # assign speckle url and get the data
        speckle_collection_received["providers"][0]["data"] = speckle_url

        CONFIG["resources"] = {
            "speckle": speckle_collection_received,
        }

    return CONFIG


def load_schema() -> dict:
    """Reads the JSON schema YAML file."""

    schema_file = THISDIR / "schemas" / "config" / "pygeoapi-config-0.x.yml"

    with schema_file.open() as fh2:
        return yaml_load(fh2)


def validate_config(instance_dict: dict) -> bool:
    """
    Validate pygeoapi configuration against pygeoapi schema

    :param instance_dict: dict of configuration

    :returns: `bool` of validation
    """

    jsonschema_validate(json.loads(to_json(instance_dict)), load_schema())

    return True


@click.group()
def config():
    """Configuration management"""
    pass


@click.command()
@click.pass_context
@click.option("--config", "-c", "config_file", help="configuration file")
def validate(ctx, config_file):
    """Validate configuration"""

    if config_file is None:
        raise click.ClickException("--config/-c required")

    with open(config_file) as ff:
        click.echo(f"Validating {config_file}")
        instance = yaml_load(ff)
        validate_config(instance)
        click.echo("Valid configuration")


config.add_command(validate)
