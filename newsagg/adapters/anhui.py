"""安徽 —— 安徽新闻网（anhui）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class AnhuiAdapter(GenericAdapter):
    name = "anhui"
    version = "1.0"
    allowed_hosts = ("www.anhuinews.com",)
    column_url = "http://www.anhuinews.com"


register(AnhuiAdapter())
