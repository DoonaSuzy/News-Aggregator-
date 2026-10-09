"""北京 —— 千龙网（beijing）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class BeijingAdapter(GenericAdapter):
    name = "beijing"
    version = "1.0"
    allowed_hosts = ("www.qianlong.com",)
    column_url = "http://www.qianlong.com/news"


register(BeijingAdapter())
