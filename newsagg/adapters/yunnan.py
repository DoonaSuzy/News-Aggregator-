"""云南 —— 云南网（yunnan）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class YunnanAdapter(GenericAdapter):
    name = "yunnan"
    version = "1.0"
    allowed_hosts = ("www.yunnan.cn",)
    column_url = "http://www.yunnan.cn"


register(YunnanAdapter())
