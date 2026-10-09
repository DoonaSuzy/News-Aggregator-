"""辽宁 —— 东北新闻网（liaoning）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class LiaoningAdapter(GenericAdapter):
    name = "liaoning"
    version = "1.0"
    allowed_hosts = ("www.nen.com.cn",)
    column_url = "http://www.nen.com.cn"


register(LiaoningAdapter())
