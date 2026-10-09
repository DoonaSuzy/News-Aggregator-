"""甘肃 —— 每日甘肃网（gansudaily）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class GansudailyAdapter(GenericAdapter):
    name = "gansudaily"
    version = "1.0"
    allowed_hosts = ("www.gansudaily.com.cn",)
    column_url = "http://www.gansudaily.com.cn"


register(GansudailyAdapter())
