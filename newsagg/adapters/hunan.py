"""湖南 —— 红网（hunan）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class HunanAdapter(GenericAdapter):
    name = "hunan"
    version = "1.0"
    allowed_hosts = ("www.rednet.cn",)
    column_url = "https://www.rednet.cn/"


register(HunanAdapter())
