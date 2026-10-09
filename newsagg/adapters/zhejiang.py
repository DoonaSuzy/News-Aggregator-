"""浙江 —— 浙江在线（zhejiang）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class ZhejiangAdapter(GenericAdapter):
    name = "zhejiang"
    version = "1.0"
    allowed_hosts = ("www.zjol.com.cn",)
    column_url = "http://www.zjol.com.cn"


register(ZhejiangAdapter())
