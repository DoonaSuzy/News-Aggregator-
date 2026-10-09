"""山西 —— 黄河新闻网（shanxi）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class ShanxiAdapter(GenericAdapter):
    name = "shanxi"
    version = "1.0"
    allowed_hosts = ("www.sxgov.cn",)
    column_url = "http://www.sxgov.cn"


register(ShanxiAdapter())
