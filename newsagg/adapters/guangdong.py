"""广东 —— 南方网（guangdong）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class GuangdongAdapter(GenericAdapter):
    name = "guangdong"
    version = "1.0"
    allowed_hosts = ("www.southcn.com",)
    column_url = "https://www.southcn.com/"


register(GuangdongAdapter())
