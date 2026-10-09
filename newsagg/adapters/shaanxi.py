"""陕西 —— 华商网（shaanxi）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class ShaanxiAdapter(GenericAdapter):
    name = "shaanxi"
    version = "1.0"
    allowed_hosts = ("www.hsw.cn",)
    column_url = "https://www.hsw.cn/"
    extra_column_urls = (
        "https://news.hsw.cn/",
    )


register(ShaanxiAdapter())
