import json
import os
from fastapi.templating import Jinja2Templates
from . import VERSION
from ._path import get_data_dir

_templates = Jinja2Templates(directory=os.path.join(get_data_dir(), "app/templates"))

class _CompatTemplates:
    def __init__(self, inner):
        self._inner = inner
        self.env = inner.env

    def TemplateResponse(self, name, context, status_code=200, headers=None, media_type=None, background=None):
        request = context.get("request")
        return self._inner.TemplateResponse(
            request, name, context,
            status_code=status_code, headers=headers,
            media_type=media_type, background=background,
        )

    def get_template(self, name):
        return self._inner.get_template(name)

templates = _CompatTemplates(_templates)
templates.env.globals["APP_VERSION"] = VERSION

def escapejs_filter(value):
    if value is None:
        return ""
    return json.dumps(str(value))[1:-1]

templates.env.filters["escapejs"] = escapejs_filter
