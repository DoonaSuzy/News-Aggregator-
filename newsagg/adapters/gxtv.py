"""广西 —— 广西网络广播电视台（gxtv）。

正文频道在 news.gxtv.cn，详情形如 /article/detail_<32位hex>.html；
首页 www.gxtv.cn 大量链接指向视频/直播与外站跳转，不适合做栏目页。
"""

from __future__ import annotations

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class GxtvAdapter(GenericAdapter):
    name = "gxtv"
    version = "1.0"
    allowed_hosts = ("news.gxtv.cn", "gxtv.cn")
    column_url = "https://news.gxtv.cn/"
    extra_column_urls = (
        "https://news.gxtv.cn/news/newsList_ce5edde7a0824569acd06d9f95577b56.html",
        "https://news.gxtv.cn/news/newsList_8c8f39167d314b29af433705c7e83dd4.html",
        "https://news.gxtv.cn/news/newsList_cae4630241cb4d74987d260020db60ad.html",
    )


register(GxtvAdapter())
