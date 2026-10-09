"""天津 —— 今晚网（jinwan）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class JinwanAdapter(GenericAdapter):
    name = "jinwan"
    version = "1.0"
    allowed_hosts = ("www.jinwan.gov.cn",)
    column_url = "https://www.jinwan.gov.cn/"
    extra_column_urls = (
        "https://www.jinwan.gov.cn/jinwan/ywdt/index.html",
        "https://www.jinwan.gov.cn/jinwan/ywdt/jwxw/index.html",
    )


register(JinwanAdapter())
