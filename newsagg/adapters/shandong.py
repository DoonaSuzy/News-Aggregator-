"""山东 —— 大众网（shandong）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class ShandongAdapter(GenericAdapter):
    name = "shandong"
    version = "1.0"
    allowed_hosts = ("www.dzwww.com",)
    column_url = "http://www.dzwww.com"


register(ShandongAdapter())
