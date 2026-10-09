"""浙江 —— 浙江在线（zhejiang）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class ZhejiangAdapter(GenericAdapter):
    name = "zhejiang"
    version = "1.0"
    allowed_hosts = ("www.zjol.com.cn", "zjol.com.cn")
    # 站点根域是 JS 壳页（8KB 无链接），正文频道在 zjnews 子域
    column_url = "https://zjnews.zjol.com.cn"
    extra_column_urls = (
        "https://china.zjol.com.cn/",
    )


register(ZhejiangAdapter())
