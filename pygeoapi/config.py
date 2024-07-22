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


def get_config(raw: bool = False, request: Request = None) -> dict:
    """
    Get pygeoapi configurations

    :param raw: `bool` over interpolation during config loading

    :returns: `dict` of pygeoapi configuration
    """

    if not os.environ.get("PYGEOAPI_CONFIG"):
        raise RuntimeError("PYGEOAPI_CONFIG environment variable not set")

    config_file = os.environ.get("PYGEOAPI_CONFIG")
    with open(config_file, encoding="utf8") as fh:
        if raw:
            CONFIG = yaml.safe_load(fh)
        else:
            CONFIG = yaml_load(fh)

    # passed url: http://localhost:5000/?limit=1000&https://app.speckle.systems/projects/55a29f3e9d/models/2d497a381d
    speckle_collection_pts = copy.deepcopy(CONFIG["resources"]["speckle"])
    speckle_collection_lines = copy.deepcopy(CONFIG["resources"]["speckle"])
    speckle_collection_polygons = copy.deepcopy(CONFIG["resources"]["speckle"])

    speckle_url = ""
    if request is not None:
        url = request.url.split("?")[-1]
        if "projects" in url and "models" in url:
            speckle_url = url

            speckle_collection_pts["title"]["en"] = "Some Points"
            speckle_collection_lines["title"]["en"] = "Some Lines"
            speckle_collection_polygons["title"]["en"] = "Some Polygons"

            # assign speckle url and get the data
            speckle_collection_pts["providers"][0]["data"] = speckle_url
            speckle_collection_lines["providers"][0]["data"] = speckle_url
            speckle_collection_polygons["providers"][0]["data"] = speckle_url

            CONFIG["resources"] = {
                "speckle": speckle_collection_pts,
                "speckle_lines": speckle_collection_lines,
                "speckle_polygons": speckle_collection_polygons,
            }

            # overwrite YAML
            with open(config_file, "r") as file:
                lines = file.readlines()
                new_lines = []
                for i, line in enumerate(lines):
                    if "data: " in line and "/projects/" in line and "/models/" in line:
                        line = f'{line.split("data: ",1)[0]}data: {speckle_url}\n'
                    new_lines.append(line)
            with open(config_file, "w") as file:
                file.writelines(new_lines)
            file.close()

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
