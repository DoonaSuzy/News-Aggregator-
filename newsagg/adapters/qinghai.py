"""青海 —— 青海新闻网（栏目用http，https会302）（qinghai）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class QinghaiAdapter(GenericAdapter):
    name = "qinghai"
    version = "1.0"
    allowed_hosts = ("www.qhnews.com",)
    column_url = "http://www.qhnews.com"


register(QinghaiAdapter())
