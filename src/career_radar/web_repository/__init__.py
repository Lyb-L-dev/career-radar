"""web_repository 包；对外保持 ``from .web_repository import ...`` 兼容。"""

from .common import _display_text, _job_type, _lines, _short_text, company_id
from .repository import WebRepository

__all__ = [
    "WebRepository",
    "company_id",
    "_display_text",
    "_job_type",
    "_lines",
    "_short_text",
]
