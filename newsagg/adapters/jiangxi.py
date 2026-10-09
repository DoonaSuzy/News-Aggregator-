"""江西 —— 大江网（需TLS SECLEVEL=1）（jiangxi）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class JiangxiAdapter(GenericAdapter):
    name = "jiangxi"
    version = "1.0"
    allowed_hosts = ("www.jxnews.com.cn",)
    column_url = "http://www.jxnews.com.cn"


register(JiangxiAdapter())
