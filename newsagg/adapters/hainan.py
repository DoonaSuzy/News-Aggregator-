"""海南 —— 南海网（hainan）。

基于通用启发式解析的适配器。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class HainanAdapter(GenericAdapter):
    name = "hainan"
    version = "1.0"
    allowed_hosts = ("www.hinews.cn",)
    column_url = "http://www.hinews.cn"
    extra_column_urls = (
        "http://www.hinews.cn/module",
        "http://www.hinews.cn/module/b0ba0a6167674227932bbeca1cc20e77",
        "http://www.hinews.cn/module/5ee709aa070c42ee8de5229dd5263b57",
    )


register(HainanAdapter())
