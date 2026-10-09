"""内蒙古 —— 正北方网（neimenggu）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class NeimengguAdapter(GenericAdapter):
    name = "neimenggu"
    version = "1.0"
    allowed_hosts = ("www.northnews.cn",)
    column_url = "http://www.northnews.cn"


register(NeimengguAdapter())
