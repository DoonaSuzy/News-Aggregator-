"""甘肃 —— 中国甘肃网（候选）（gansu）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class GansuAdapter(GenericAdapter):
    name = "gansu"
    version = "1.0"
    allowed_hosts = ("www.gscn.com.cn",)
    column_url = "http://www.gscn.com.cn"


register(GansuAdapter())
