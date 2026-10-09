"""四川 —— 四川新闻网（sichuan）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class SichuanAdapter(GenericAdapter):
    name = "sichuan"
    version = "1.0"
    allowed_hosts = ("www.newssc.org",)
    column_url = "http://www.newssc.org"
    extra_column_urls = (
        "https://scnews.newssc.org/",
        "https://city.newssc.org/",
    )


register(SichuanAdapter())
