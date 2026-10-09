"""北京 —— 千龙网（beijing）。

栏目页用站点根域：/news 子路径对爬虫返回 403，根域可正常取到头条列表。
正文分布在 china./beijing. 子域，形如 /2026/1009/8736408.shtml。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class BeijingAdapter(GenericAdapter):
    name = "beijing"
    version = "1.0"
    allowed_hosts = ("www.qianlong.com",)
    column_url = "https://www.qianlong.com/"


register(BeijingAdapter())
