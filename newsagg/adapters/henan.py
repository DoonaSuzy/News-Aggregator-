"""河南 —— 大河网（henan）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class HenanAdapter(GenericAdapter):
    name = "henan"
    version = "1.0"
    allowed_hosts = ("www.dahe.cn",)
    column_url = "https://www.dahe.cn/"


register(HenanAdapter())
