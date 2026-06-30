import json
from fastapi.templating import Jinja2Templates
from . import VERSION

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["APP_VERSION"] = VERSION

def escapejs_filter(value):
    if value is None:
        return ""
    return json.dumps(str(value))[1:-1]

templates.env.filters["escapejs"] = escapejs_filter
