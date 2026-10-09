"""湖北 —— 荆楚网（候选）（hubei）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class HubeiAdapter(GenericAdapter):
    name = "hubei"
    version = "1.0"
    allowed_hosts = ("www.cnhubei.com",)
    column_url = "http://www.cnhubei.com"


register(HubeiAdapter())
