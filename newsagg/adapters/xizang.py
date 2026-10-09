"""西藏 —— 中国西藏新闻网（xizang）。

栏目页 chinatibetnews.com 会跳转到 xzxw.com，正文全部落在 xzxw.com，
详情形如 /xw/gnyw/2026-10/08/content_6963241.html。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class XizangAdapter(GenericAdapter):
    name = "xizang"
    version = "1.0"
    allowed_hosts = ("www.xzxw.com", "xzxw.com", "www.chinatibetnews.com",
                     "chinatibetnews.com")
    column_url = "https://www.xzxw.com"
    extra_column_urls = (
        "https://www.xzxw.com/xw/",
        "https://www.xzxw.com/zw/",
    )


register(XizangAdapter())
