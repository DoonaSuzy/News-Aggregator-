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
#
# 覆盖实测到的省级站点形态：
# - content_\d+              xizang  /xw/gnyw/2026-10/08/content_6963241.html
# - /\d{4}[-/]\d{1,2}[-/]..  hubei   /content/2026-10/09/content_20228018.html
# - /\d{4}/\d{2}[-/]\d{2}    henan   /2026/10-06/2138276.html
# - /\d{6,}/                 jilin   /gnyw/202610/4088400.html、hunan /nograb/646054/
# - /t\d{6,}\.s?html?$       changjiang /asy/ttxw/202610/t5347644.htm
# - /\d{5,}\.s?html?$        liaoning/shaanxi/gansudaily/sichuan/jiangxi
# - system/\d{8}             sichuan /system/20261009/001646227.html
# - /node_xxx/yyy.shtml      guangdong（南方网）详情页
_ARTICLE_HINT = re.compile(
    r"(content_\d+"
    r"|/\d{4}[-/]\d{1,2}[-/]\d{1,2}[-/]"
    r"|/\d{4}/\d{2}[-/]\d{2}[-/]"
    r"|/\d{6,}/"
    r"|/t\d{6,}\.s?html?$"
    r"|/\d{5,}\.s?html?$"
    r"|system/\d{8}"
    r"|/t20\d{6}"
    r"|article|/detail|/news/\d"
    r"|/node_[0-9a-z]+/[0-9a-z]+\.s?html"
    r"|/content/[0-9a-z_-]{6,}\.s?html?$"
    r")",
    re.I,
)
# 应排除的链接（栏目/专题/功能页/节点页）
# 注意：节点页只在「以节点段结尾」时才排除，南方网详情形如 /node_xxx/yyy.shtml 不能误杀
_SKIP_HINT = re.compile(
    r"(javascript:|mailto:|#|/tag/|/special/|/zhuanti|/video/|/photo/|/live/|/roll|"
    r"/list|/node_[0-9a-z]+/?$|/node_[0-9a-z]+\.s?html?$|/a/|/gov|"
    r"index\.s?html?$|/$|sitemap|/home/|/channel|/column|/about)",
    re.I,
)


# 页脚/版权/导航等噪声短段（仅在段落较短时才据此剔除）
_FOOTER_HINT = re.compile(
    r"(版权所有|Copyright|ICP|备案号|主办单位|承办单位|技术支持|友情链接|"
    r"责任编辑|扫一扫|分享到|上一条|下一条|阅读次数|来源：\s*$)",
    re.I,
)

#: 元数据噪声：6 位以上连续数字（文章 id / 时间戳 / 图集计数）
_META_NOISE = re.compile(r"\d{6,}")
#: 中文句子标点：出现则该行更可能是正文而非纯元数据
_SENTENCE_PUNCT = re.compile(r"[。！？；，、：""''《》（)()]")


#: URL 里内嵌的发布日期。省级站普遍把日期写进路径，页面无时间字样时可兜底。
#   例：/t20220329_24006101.shtml、/system/2026/10/09/、/20261009/、
#       /2024-03/05/、/content_20260305
_URL_DATE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/t(\d{4})(\d{2})(\d{2})(?:_\d+)?\.s?html?$", re.I), "y-m-d"),
    (re.compile(r"/(\d{4})(\d{2})(\d{2})[/_-]"), "y-m-d"),
    (re.compile(r"/(\d{4})[-/](\d{1,2})[-/](\d{1,2})[/_-]"), "y-m-d"),
    (re.compile(r"[/_](\d{4})(\d{2})(\d{2})\.s?html?$", re.I), "y-m-d"),
)


def _time_from_url(url: str) -> str:
    """从 URL 抽发布日期，返回 ``YYYY-MM-DD``；抽不到返回空串。"""
    for pat, _ in _URL_DATE_PATTERNS:
        m = pat.search(url)
        if not m:
            continue
        y, mo, d = (int(g) for g in m.groups())
        if not (1995 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
            continue
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


class GenericAdapter:
    """通用站点适配器。子类只需设置类属性。"""

    name: str = ""
    version: str = "1.0"
    allowed_hosts: tuple[str, ...] = ()
    column_url: str = ""
    #: 同站其他新闻频道入口（要闻/时政/本地…）。单个栏目页往往只有十几条
    #: 候选，扩频道是提升覆盖最省事的办法；爬虫会把它们和 column_url 一起
    #: 当作本次任务的起始页。留空表示只用 column_url。
    extra_column_urls: tuple[str, ...] = ()
    #: 单来源请求间隔（秒），贵州等限流站点覆写为 5
    request_interval: float = 0.0
    #: 该来源专用 TLS 密码套件（OpenSSL 语法）。少数老站（如大江网）只支持
    #: 弱套件，默认上下文握手会直接 SSLV3_ALERT_HANDSHAKE_FAILURE；只有明确
    #: 声明的来源才降级，证书校验照旧开启。
    tls_ciphers: str | None = None

    # 详情页 URL 判定（覆盖默认）
    article_pattern: re.Pattern[str] = _ARTICLE_HINT
    # 正文容器候选选择器（按优先级）
    body_selectors: tuple[str, ...] = (
        "div.TRS_Editor", "div.article-content", "div#content", "div.content",
        "div.article", "div#articleContent", "div.text", "article",
        "div.main-content", "div.news_content", "div.cont", "div.dtu_neir",
        "div.articleCon", "div.article-body", "div.news-con", "div.articlecont",
        "div.Custom_UnionStyle", "div#zoom", "div.gray", "div.contTxt",
        "div.Newsfont", "div.TxtContent", "div.view_content",
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
        """判断 URL 是否属于本站。

        省级站点的正文常分布在子域（news./china./hn./moment. 等），
        因此除 ``allowed_hosts`` 精确/后缀匹配外，还把 ``www.x.y`` 派生出的
        父域 ``x.y`` 视为同源（如 www.rednet.cn → hn.rednet.cn 也放行）。
        """
        host = urlsplit(url).netloc.lower().split(":")[0]
        for raw in self.allowed_hosts:
            h = raw.lower()
            if host == h or host.endswith("." + h):
                return True
            if h.startswith("www."):
                parent = h[4:]
                if host == parent or host.endswith("." + parent):
                    return True
        return False

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
        if not source_name:
            # 选择器没命中时，正文里几乎都有「来源：xxx」字样，全文扫一遍兜底
            source_name = self._clean_source(self._scan_source_in_text(html))
        published_text = self._first_text(sel, self.time_selectors)
        if not published_text:
            published_text = self._scan_time_in_text(html)
        if not published_text:
            # 页面里完全没有时间字样时（浙江在线专题页、部分 CMS 模板），
            # 省级站的 URL 本身几乎都带日期，这是最后一层兜底。
            published_text = _time_from_url(url)
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
            p_chars = sum(len(p) for p in paras)
            # 块级切分：兼容正文为裸文本节点的站点（如东南网 neir 容器，
            # 段落由 <br>/<p> 分隔但不全被 <p> 包裹）。取信息量更大者。
            blocks = self._split_container_blocks(node[0])
            block_chars = sum(len(p) for p in blocks)
            if blocks and block_chars >= p_chars:
                return blocks
            if paras:
                return paras
            # 容器无 <p> 时取整块文本
            text = " ".join(node.css("::text").getall()).strip()
            if text and len(text) >= 20:
                return [text]
        # 站点没有常见正文容器（云南网、辽宁东北新闻网、华龙网…）时，
        # 退回全文 <p> 密度法：滤掉导航/页脚后仍有足量文字就当作正文。
        return self._fallback_paragraphs(sel)

    def _split_container_blocks(self, node) -> list[str]:
        """把正文容器按块级标签（<br>/<p>/<div> 等）切成段落。

        很多省级站把正文写成裸文本节点，用 <br> 或换行分隔段落，而不是用
        <p> 包裹。这里把容器原始 HTML 里的块级边界当作段落分隔，剥离标签
        后得到正文行，再按长度/链接占比/页脚特征过滤。
        """
        import re as _re
        raw = node.get() or ""
        if not raw:
            return []
        # 去掉 script/style，避免把脚本文本当正文
        raw = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=_re.I | _re.S)
        # 块级分隔符：<br>、</p>、</div>、</td>、</li>、开标签 <p ...>/<div ...>
        raw = _re.sub(r"<br\s*/?>", "\n", raw, flags=_re.I)
        raw = _re.sub(r"</p>|</div>|</td>|</li>|</h[1-6]>", "\n", raw, flags=_re.I)
        # 完整开标签（含属性）当作段落边界，避免 class="..." 等属性残留成文本
        raw = _re.sub(r"<p\b[^>]*>|<div\b[^>]*>|<td\b[^>]*>|<li\b[^>]*>|<h[1-6]\b[^>]*>",
                      "\n", raw, flags=_re.I)
        # 去零宽字符
        raw = _re.sub(r"[\u200b\u200c\u200d\ufeff]", "", raw)
        # 去剩余标签
        raw = _re.sub(r"<[^>]+>", " ", raw)
        # 反转义常见实体
        for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                        ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
            raw = raw.replace(ent, ch)
        raw = _re.sub(r"[ \t\u00a0]+", " ", raw)
        lines: list[str] = []
        for seg in raw.splitlines():
            text = seg.strip()
            if len(text) < 8:
                continue
            # 页脚/版权等短噪声段剔除；较长段落即使含关键词也保留
            if _FOOTER_HINT.search(text) and len(text) < 80:
                continue
            # 尾部元数据噪声：含 6 位以上连续数字串（文章 id/时间戳/图集计数）
            # 且整段无中文句子标点，通常不是正文
            if _META_NOISE.search(text) and not _SENTENCE_PUNCT.search(text):
                continue
            lines.append(text)
        return lines

    def _fallback_paragraphs(self, sel: Selector) -> list[str]:
        """全文 <p> 兜底：按长度、链接占比、页脚特征筛出正文段落。"""
        paras: list[str] = []
        for p in sel.css("p"):
            text = " ".join(p.css("::text").getall()).strip()
            if len(text) < 15:
                continue
            link_text = "".join(p.css("a::text").getall()).strip()
            # 整段都是链接 → 导航 / 相关阅读
            if link_text and len(link_text) > len(text) * 0.6:
                continue
            if _FOOTER_HINT.search(text) and len(text) < 80:
                continue
            paras.append(text)
        if sum(len(p) for p in paras) >= 120:
            return paras
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

    def _scan_source_in_text(self, html: str) -> str:
        """来源兜底：去标签后在全文里找「来源：xxx」。"""
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        match = re.search(r"来源\s*[：:]\s*([^\s]{2,25})", text)
        if match:
            return match.group(1).strip()
        return ""

    def _scan_time_in_text(self, html: str) -> str:
        # 先剔除脚本/样式块：JS 里的 URL 片段（如 /646054/98/16345105）
        # 极易被宽泛正则误当日期，导致正文时间被污染成 6054/98/16345105。
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        # 优先匹配带时分的完整发布时间（真实发布时间几乎都含 HH:MM，
        # 而 URL/ID 片段极少带冒号），命中即返回。
        m = re.search(
            r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?[ T]\d{1,2}:\d{2}(?::\d{2})?",
            text,
        )
        if m:
            return m.group(0)
        # 退化：仅日期（需年月日三段，避免吞数字 ID）
        m = re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?", text)
        return m.group(0) if m else ""


__all__ = ["GenericAdapter"]
