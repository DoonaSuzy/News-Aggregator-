"""通用启发式适配器基类。

为 31 个启用来源 + 3 个候选来源提供基于常见新闻站点的解析：
- 列表页：提取指向详情页的 <a> 链接（标题 + URL），推断下一页。
- 详情页：在常见正文容器中提取标题、段落、来源、时间。

各站点可通过覆写钩子微调（选择器、host、详情 URL 判定等）。
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from parsel import Selector

from newsagg.adapters.base import DetailParse, ListItem, ListParse
from newsagg.adapters.listing import mark_sticky
from newsagg.cleaning import clean_title, extract_source, looks_like_source


# 详情 URL 常见特征（需命中其一且不在排除列表）
_ARTICLE_HINT = re.compile(
    r"(content_\d+|/\d{4}-\d{2}/\d{2}/|/\d{6}/|/\d{5,}|/t20\d{6}|article|/news/\d|/detail)",
    re.I,
)
# 应排除的链接（栏目/专题/功能页/节点页）
_SKIP_HINT = re.compile(
    r"(javascript:|mailto:|#|/tag/|/special/|/zhuanti|/video/|/photo/|/live/|/roll|"
    r"/list|/node_|/a/|/gov|index\.s?html?$|/$|sitemap|/home/|/channel|/column|/about)",
    re.I,
)


class GenericAdapter:
    """通用站点适配器。子类只需设置类属性。"""

    name: str = ""
    version: str = "1.0"
    allowed_hosts: tuple[str, ...] = ()
    column_url: str = ""
    #: 单来源请求间隔（秒），贵州等限流站点覆写为 5
    request_interval: float = 0.0

    # 详情页 URL 判定（覆盖默认）
    article_pattern: re.Pattern[str] = _ARTICLE_HINT
    # 正文容器候选选择器（按优先级）
    body_selectors: tuple[str, ...] = (
        "div.TRS_Editor", "div.article-content", "div#content", "div.content",
        "div.article", "div#articleContent", "div.text", "article",
        "div.main-content", "div.news_content", "div.cont", "div.dtu_neir",
        "div.articleCon", "div.article-body", "div.news-con", "div.articlecont",
        "div.Custom_UnionStyle", "div#zoom", "div.gray", "div.contTxt",
    )
    title_selectors: tuple[str, ...] = (
        "h1", "h1.title", "div.title h1", "div.article-title", "div.news-title",
        "div.dtu_bt", "div.cont-title", "div.h-title", "div.art-title",
    )
    source_selectors: tuple[str, ...] = (
        "span.source", "div.source", "span.source-name", "div.news-source",
        "span.where", "div.info span", "div.dtu_zj", "span.editor", "div.zuoze",
    )
    time_selectors: tuple[str, ...] = (
        "span.time", "div.time", "span.pubtime", "div.pubtime", "span.date",
        "div.info span.time", "div.article-info span", "div.dtu_zj", "span.timer",
    )

    # ---- URL 判定 -----------------------------------------------------

    def allows(self, url: str) -> bool:
        host = urlsplit(url).netloc.lower()
        return any(host == h or host.endswith("." + h) for h in self.allowed_hosts)

    def is_article(self, url: str) -> bool:
        if not self.allows(url):
            return False
        if _SKIP_HINT.search(url):
            return False
        return bool(self.article_pattern.search(url))

    # ---- 列表解析 -----------------------------------------------------

    def parse_list(self, html: str, *, base_url: str) -> ListParse:
        sel = Selector(text=html)
        items: list[ListItem] = []
        seen: set[str] = set()
        for a in sel.css("a"):
            href = a.attrib.get("href", "")
            if not href:
                continue
            abs_url = urljoin(base_url, href)
            if _SKIP_HINT.search(abs_url):
                continue
            if not self.is_article(abs_url):
                continue
            if abs_url in seen:
                continue
            title = " ".join(a.css("::text").getall()).strip()
            if not title or len(title) < 4:
                continue
            seen.add(abs_url)
            items.append(ListItem(url=abs_url, title=title, list_time_text=""))
        mark_sticky(items)
        next_url = self._find_next(sel, base_url)
        return ListParse(items=items, next_url=next_url, descending=True)

    def _find_next(self, sel: Selector, base_url: str) -> str | None:
        for a in sel.css("a"):
            text = " ".join(a.css("::text").getall()).strip()
            if text in ("下一页", "下页", "next", "Next", "»", "›>"):
                href = a.attrib.get("href", "")
                if href:
                    return urljoin(base_url, href)
        return None

    # ---- 详情解析 -----------------------------------------------------

    def parse_detail(self, html: str, *, url: str) -> DetailParse:
        sel = Selector(text=html)
        title = self._first_text(sel, self.title_selectors) or self._title_from_head(sel)
        paragraphs = self._extract_paragraphs(sel)
        raw_source = self._first_text(sel, self.source_selectors)
        source_name = self._clean_source(raw_source)
        published_text = self._first_text(sel, self.time_selectors)
        if not published_text:
            published_text = self._scan_time_in_text(html)
        media_only = len(paragraphs) == 0
        return DetailParse(
            title=title,
            paragraphs=paragraphs,
            source_name=source_name,
            published_text=published_text,
            media_only=media_only,
        )

    def _title_from_head(self, sel: Selector) -> str:
        """标题兜底：先 og:title，再 <title>（去掉站点名后缀）。"""
        og = sel.css("meta[property='og:title']::attr(content)").get()
        if og and len(og.strip()) >= 4:
            return og.strip()
        t = sel.css("title::text").get()
        if t:
            t = clean_title(t)
            # 去掉常见「标题 - 站点名」/「标题_站点名」后缀
            t = re.split(r"\s+[-_|—]\s+", t)[0].strip()
            if len(t) >= 4:
                return t
        return ""

    def _clean_source(self, raw: str) -> str:
        """用 extract_source 清洗；结果不像媒体名则丢弃。"""
        cleaned = extract_source(raw)
        if cleaned and looks_like_source(cleaned):
            return cleaned
        return cleaned if cleaned and len(cleaned) <= 20 else ""


    def _extract_paragraphs(self, sel: Selector) -> list[str]:
        for selector in self.body_selectors:
            node = sel.css(selector)
            if not node:
                continue
            paras = [
                " ".join(p.css("::text").getall()).strip()
                for p in node.css("p")
            ]
            paras = [p for p in paras if p and len(p) >= 8]
            if paras:
                return paras
            # 容器无 <p> 时取整块文本
            text = " ".join(node.css("::text").getall()).strip()
            if text and len(text) >= 20:
                return [text]
        return []

    def _first_text(self, sel: Selector, selectors: tuple[str, ...]) -> str:
        """提取首个匹配元素的文本。

        优先取元素自身的直接文本节点，再退化为后代文本合并，
        避免把整块正文容器当成标题。
        """
        for selector in selectors:
            nodes = sel.css(selector)
            if not nodes:
                continue
            node = nodes[0]
            # 直接文本节点优先（不含后代元素文本）
            own = "".join(node.css("::text").getall()).strip()
            if own:
                return own
            # 否则取第一个有意义的后代文本
            for text in node.css("*::text").getall():
                text = text.strip()
                if len(text) >= 2:
                    return text
        return ""

    def _scan_time_in_text(self, html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html)
        match = re.search(
            r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?[ T]?\d{0,2}:?\d{0,2}:?\d{0,2}",
            text,
        )
        return match.group(0) if match else ""


__all__ = ["GenericAdapter"]
