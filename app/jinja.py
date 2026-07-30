import json
import os
from fastapi.templating import Jinja2Templates
from . import VERSION
from ._path import get_data_dir
from .constants import (
    InvoiceStatus, INVOICE_STATUS_LABELS,
    INVOICE_STATUS_BADGES, INVOICE_STATUS_ROW_CLASS,
    INVOICE_STATUS_CHOICES,
)

_templates = Jinja2Templates(directory=os.path.join(get_data_dir(), "app/templates"))

class _CompatTemplates:
    def __init__(self, inner):
        self._inner = inner
        self.env = inner.env

    def TemplateResponse(self, name, context, status_code=200, headers=None, media_type=None, background=None):
        request = context.get("request")
        if request and hasattr(request.state, 'community_address') and 'community_address' not in context:
            context['community_address'] = request.state.community_address
        return self._inner.TemplateResponse(
            request, name, context,
            status_code=status_code, headers=headers,
            media_type=media_type, background=background,
        )

    def get_template(self, name):
        return self._inner.get_template(name)

templates = _CompatTemplates(_templates)
templates.env.globals["APP_VERSION"] = VERSION
templates.env.globals["INVOICE_STATUS_CHOICES"] = INVOICE_STATUS_CHOICES

def escapejs_filter(value):
    if value is None:
        return ""
    return json.dumps(str(value))[1:-1]

templates.env.filters["escapejs"] = escapejs_filter

templates.env.filters["status_label"] = lambda s: INVOICE_STATUS_LABELS.get(s, s)
templates.env.filters["status_badge"] = lambda s: INVOICE_STATUS_BADGES.get(s, "badge bg-secondary")
templates.env.filters["status_row_class"] = lambda s: INVOICE_STATUS_ROW_CLASS.get(s, "")

def _invoice_status_test(value, name):
    try:
        return value == getattr(InvoiceStatus, name.upper()).value
    except (KeyError, AttributeError):
        return False
templates.env.tests["invoice_status"] = _invoice_status_test
