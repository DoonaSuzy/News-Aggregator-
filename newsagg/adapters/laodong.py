"""上海 —— 劳动报（站内shsldb稿）（laodong）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class LaodongAdapter(GenericAdapter):
    name = "laodong"
    version = "1.0"
    allowed_hosts = ("www.51ldb.com",)
    column_url = "https://www.51ldb.com/shsldb/"


register(LaodongAdapter())
