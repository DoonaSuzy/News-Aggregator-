"""黑龙江 —— 黑龙江新闻网（heilongjiang）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class HeilongjiangAdapter(GenericAdapter):
    name = "heilongjiang"
    version = "1.0"
    allowed_hosts = ("www.hljnews.cn",)
    column_url = "http://www.hljnews.cn"


register(HeilongjiangAdapter())
