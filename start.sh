source .venv/bin/activate

export PYGEOAPI_CONFIG="example-config.yml"
export PYGEOAPI_OPENAPI="example-openapi.yml"
export MAPTILER_KEY_SPECKLE="qam9vwl7bVk5tW1oZu46"
export PORT=8000

gunicorn pygeoapi.flask_app:APP --timeout 100000 --access-logfile access_log --error-logfile error_log --capture-output
