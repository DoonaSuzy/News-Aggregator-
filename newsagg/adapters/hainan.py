"""海南 —— 南海网（hainan）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class HainanAdapter(GenericAdapter):
    name = "hainan"
    version = "1.0"
    allowed_hosts = ("www.hinews.cn",)
    column_url = "http://www.hinews.cn"


register(HainanAdapter())
