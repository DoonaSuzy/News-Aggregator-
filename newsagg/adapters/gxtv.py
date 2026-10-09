"""广西 —— 广西网络广播电视台（gxtv）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class GxtvAdapter(GenericAdapter):
    name = "gxtv"
    version = "1.0"
    allowed_hosts = ("www.gxtv.cn",)
    column_url = "http://www.gxtv.cn"


register(GxtvAdapter())
