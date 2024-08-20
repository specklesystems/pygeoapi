# pygeoapi

[![DOI](https://zenodo.org/badge/121585259.svg)](https://zenodo.org/badge/latestdoi/121585259)
[![Build](https://github.com/geopython/pygeoapi/actions/workflows/main.yml/badge.svg)](https://github.com/geopython/pygeoapi/actions/workflows/main.yml)
[![Docker](https://github.com/geopython/pygeoapi/actions/workflows/containers.yml/badge.svg)](https://github.com/geopython/pygeoapi/actions/workflows/containers.yml)
[![Vulnerabilities](https://github.com/geopython/pygeoapi/actions/workflows/vulnerabilities.yml/badge.svg)](https://github.com/geopython/pygeoapi/actions/workflows/vulnerabilities.yml)

[pygeoapi](https://pygeoapi.io) is a Python server implementation of the [OGC API](https://ogcapi.ogc.org) suite of standards. The project emerged as part of the next generation OGC API efforts in 2018 and provides the capability for organizations to deploy a RESTful OGC API endpoint using OpenAPI, GeoJSON, and HTML. pygeoapi is [open source](https://opensource.org/) and released under an [MIT license](https://github.com/geopython/pygeoapi/blob/master/LICENSE.md).

Please read the docs at [https://docs.pygeoapi.io](https://docs.pygeoapi.io) for more information.

## Speckle plugin

Launch:
```python
// python -m venv pygeoapi_venv
cd pygeoapi_venv
Scripts\activate
cd pygeoapi
// git clone https://github.com/specklesystems/pygeoapi
cd pygeoapi
git checkout dev
git reset --hard dev
// pip install --upgrade pip
// pip install -r requirements.txt
python setup.py install
set PYGEOAPI_CONFIG=example-config.yml // export
set PYGEOAPI_OPENAPI=example-config.yml // export
set MAPTILER_KEY_LOCAL=your_api_key // export, (if available)
pygeoapi openapi generate $PYGEOAPI_CONFIG > $PYGEOAPI_OPENAPI
pygeoapi serve
```

Example URL:
http://localhost:5000/?limit=10000&speckleUrl=https://app.speckle.systems/projects/55a29f3e9d/models/2d497a381d

If GIS-originated Speckle model is loaded, no additional arguments are needed, except SPECKLEURL and LIMIT. 

Supported arguments:
 - speckleUrl (text) - required, should contain path to a specific Model in Speckle Project, e.g. 'https://app.speckle.systems/projects/55a29f3e9d/models/2d497a381d'
 - limit (positive integer), recommended, as some applications might apply their custom feature limit
 - crsAuthid (text), an authority string e.g. 'epsg:4326'. If set, LAT, LON and NORTHDEGREES arguments will be ignored.
 - lat (number), in range -90 to 90
 - lon (number), in range -180 to 180
 - northDegrees (number), in range -180 to 180

