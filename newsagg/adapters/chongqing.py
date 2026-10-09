"""重庆 —— 华龙网（chongqing）。试点站点之一，配有 HTML 夹具。

已知：栏目页没有更早的历史入口，可见范围从当次列表最旧一条算起。
"""

from __future__ import annotations

import re

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class ChongqingAdapter(GenericAdapter):
    name = "chongqing"
    version = "1.0"
    allowed_hosts = ("www.cqnews.net", "cqnews.net")
    column_url = "http://www.cqnews.net"

    article_pattern = re.compile(r"/\d{4}-\d{2}/\d{2}/content_\d+|/\.s?html?$", re.I)
    body_selectors = ("div.TRS_Editor", "div#content", "div.article-content", "div.content")
    title_selectors = ("h1", "div.title h1")
    source_selectors = ("span.source", "div.source", "div.info span")
    time_selectors = ("span.time", "div.time", "div.info span")


register(ChongqingAdapter())
