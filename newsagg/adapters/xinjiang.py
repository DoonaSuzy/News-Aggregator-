"""新疆 —— 新疆网（xinjiang）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class XinjiangAdapter(GenericAdapter):
    name = "xinjiang"
    version = "1.0"
    allowed_hosts = ("www.xinjiangnet.com.cn",)
    column_url = "https://www.xinjiangnet.com.cn/"
    extra_column_urls = (
        "https://www.xinjiangnet.com.cn/sy/jnxw/",
        "https://www.xinjiangnet.com.cn/xjdz/",
    )


register(XinjiangAdapter())
