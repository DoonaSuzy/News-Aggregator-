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
    column_url = "http://www.xinjiangnet.com.cn"


register(XinjiangAdapter())
