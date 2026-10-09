"""西藏 —— 中国西藏新闻网（xizang）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class XizangAdapter(GenericAdapter):
    name = "xizang"
    version = "1.0"
    allowed_hosts = ("www.chinatibetnews.com",)
    column_url = "http://www.chinatibetnews.com"


register(XizangAdapter())
