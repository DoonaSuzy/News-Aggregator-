"""吉林 —— 中国吉林网（jilin）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class JilinAdapter(GenericAdapter):
    name = "jilin"
    version = "1.0"
    allowed_hosts = ("www.cnjiwang.com",)
    column_url = "http://www.cnjiwang.com"


register(JilinAdapter())
