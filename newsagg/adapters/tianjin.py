"""天津 —— 北方网（候选）（tianjin）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class TianjinAdapter(GenericAdapter):
    name = "tianjin"
    version = "1.0"
    allowed_hosts = ("news.enorth.com.cn",)
    column_url = "http://news.enorth.com.cn"


register(TianjinAdapter())
