"""河北 —— 河北新闻网（hebei）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class HebeiAdapter(GenericAdapter):
    name = "hebei"
    version = "1.0"
    allowed_hosts = ("www.hebnews.cn",)
    column_url = "http://www.hebnews.cn"


register(HebeiAdapter())
