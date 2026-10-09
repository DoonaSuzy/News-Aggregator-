"""江苏 —— 中国江苏网（jiangsu）。

试点站点之一，配有 HTML 夹具。
已知：要闻嵌入列表到不了窗口第一天 0 点，任务保持 partial。
"""

from __future__ import annotations

import re

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class JiangsuAdapter(GenericAdapter):
    name = "jiangsu"
    version = "1.0"
    allowed_hosts = ("www.jschina.com.cn", "jsnews.jschina.com.cn")
    column_url = "https://www.jschina.com.cn/"

    article_pattern = re.compile(r"jschina\.com\.cn.*?/\d{5,}/?|/\.s?html?$", re.I)
    body_selectors = (
        "div.TRS_Editor", "div#content", "div.article-content", "div.content",
    )
    title_selectors = ("h1", "div.title h1", "div.article-title")
    source_selectors = ("span.source", "div.source", "div.title span", "div.info span")
    time_selectors = ("span.time", "div.time", "div.info span", "div.title span")


register(JiangsuAdapter())

