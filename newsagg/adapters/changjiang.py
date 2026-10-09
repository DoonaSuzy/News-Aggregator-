"""湖北 —— 长江网（changjiang）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class ChangjiangAdapter(GenericAdapter):
    name = "changjiang"
    version = "1.0"
    allowed_hosts = ("www.cjn.cn",)
    column_url = "http://www.cjn.cn"
    extra_column_urls = (
        "http://news.cjn.cn/whpd/",
        "http://news.cjn.cn/hbpd_19912/",
        "http://news.cjn.cn/cqpd/",
    )


register(ChangjiangAdapter())
