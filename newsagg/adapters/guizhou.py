"""贵州 —— 当代先锋网（限流5秒/并发1，忽略robots）（guizhou）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class GuizhouAdapter(GenericAdapter):
    name = "guizhou"
    version = "1.0"
    allowed_hosts = ("www.ddxfw.cn",)
    column_url = "http://www.ddxfw.cn"
    request_interval = 5

register(GuizhouAdapter())
