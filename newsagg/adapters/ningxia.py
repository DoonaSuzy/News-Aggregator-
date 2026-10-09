"""宁夏 —— 银川新闻网（ningxia）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class NingxiaAdapter(GenericAdapter):
    name = "ningxia"
    version = "1.0"
    allowed_hosts = ("www.ycen.com.cn",)
    column_url = "http://www.ycen.com.cn"


register(NingxiaAdapter())
