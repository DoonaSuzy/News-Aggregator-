"""福建 —— 东南网（fujian）。试点站点之一，配有 HTML 夹具。

页面结构：标题 div.dtu_bt，正文 div.dtu_neir(含<p>)，
时间/来源 div.dtu_zj（含"来源：xxx"与编辑信息）。
"""

from __future__ import annotations

import re

from newsagg.adapters._common import GenericAdapter
from newsagg.adapters import register


class FujianAdapter(GenericAdapter):
    name = "fujian"
    version = "1.0"
    allowed_hosts = ("www.fjsen.com", "fjsen.com")
    column_url = "http://www.fjsen.com"

    article_pattern = re.compile(r"/\d{4}-\d{2}/\d{2}/content_\d+", re.I)
    body_selectors = ("div.dtu_neir", "div.TRS_Editor", "div#content", "div.content")
    title_selectors = ("div.dtu_bt", "h1", "div.title h1")
    source_selectors = ("span.source", "div.dtu_zj span", "a[href*='source']", "div.dtu_zj")
    time_selectors = ("div.dtu_zj", "span.time", "div.time")

    def parse_detail(self, html, *, url):
        from newsagg.adapters.base import DetailParse

        parsed = super().parse_detail(html, url=url)
        # dtu_zj 里混杂时间与来源，从文本中抽出"来源：xxx"
        block = self._raw_dtu_zj(html)
        if block:
            m = re.search(r"来源[：:]\s*([^\s<\d][^<\n]{1,40})", block)
            if m:
                parsed.source_name = m.group(1).strip()
        return parsed

    @staticmethod
    def _raw_dtu_zj(html: str) -> str:
        from parsel import Selector

        sel = Selector(text=html)
        return " ".join(sel.css("div.dtu_zj ::text").getall())


register(FujianAdapter())
