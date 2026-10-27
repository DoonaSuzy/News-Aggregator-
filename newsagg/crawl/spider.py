"""站点蜘蛛：``SiteSpider``（Scrapy Spider）。

职责：
- ``async start()`` 是真实入口（Scrapy 2.13+ 要求），同时保留 ``start_requests()``。
- ``parse_list``：翻页 + 落库候选；命中窗口上界/倒序破坏则停止。
- ``parse_detail``：处理 404/410/非文本/解析失败；多页正文拼接；窗口上界过滤。
- ``_guard()``：租约丢失、被封、超预算时关闭蜘蛛。
- ``on_error``：分类失败原因并写失败页样本。

蜘蛛只负责“抓 + 解析 + 交给 session 落库”，不直接写 SQL。
"""

from __future__ import annotations


import re

import scrapy

from newsagg.adapters import ensure_loaded, get_adapter
from newsagg.adapters.base import DetailParse
from newsagg.cleaning import (
    clean_paragraphs,
    clean_source,
    clean_title,
    content_hash,
    parse_published,
    quality_flags,
    to_utc_naive,
)
from newsagg.crawl.mimetypes import is_non_text_page
from newsagg.crawl.sampler import Sampler
from newsagg.crawl.session import CrawlSession
from newsagg.logutil import get_logger
from newsagg.timeguard import clamp_published
from newsagg.urls import normalize_url, url_hash

log = get_logger()

#: 纯 JS 跳转壳页：<script>location.href = "..."</script>
#: 典型如 world.newssc.org（四川）——静态正文为空，真实稿件在
#: h.xinhuaxmt.com 上，不跟随就只能存一条空壳记录。
_JS_REDIRECT = re.compile(
    r"""(?:location\.href|window\.location|location\.replace)\s*=\s*["']([^"']+)["']""",
    re.I,
)
#: 壳页体积上限：正文页不可能只有这么点内容
_SHELL_MAX_BYTES = 4096


def js_redirect_target(text: str) -> str:
    """壳页里唯一的 JS 跳转目标；非壳页返回空串。"""
    if not text or len(text) > _SHELL_MAX_BYTES:
        return ""
    m = _JS_REDIRECT.search(text)
    return m.group(1).strip() if m else ""


class SiteSpider(scrapy.Spider):
    """单站点抓取蜘蛛。``session`` 由 engine 注入。"""

    name = "site_spider"

    def __init__(self, session: CrawlSession, column_url: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session
        self.column_url = column_url
        self.adapter_name = session.adapter_name
        ensure_loaded()
        self.adapter = get_adapter(session.adapter_name)
        self.sampler = Sampler(str(session.settings.resolved_log_dir))
        self._page_url = column_url
        self._visited_pages: set[str] = set()

    # --- 入口 -------------------------------------------------------------

    def _entry_urls(self) -> list[str]:
        """本次任务的入口栏目页。

        主栏目页之外，适配器可用 ``extra_column_urls`` 追加同站的其他新闻频道
        （要闻/时政/本地…）。只爬一个栏目页时，很多省级站点只能拿到十几条候选，
        扩频道是提升覆盖最直接的办法。
        """
        urls = [self.column_url]
        extra = getattr(self.adapter, "extra_column_urls", ()) or ()
        for u in extra:
            if u and u not in urls:
                urls.append(u)
        return urls

    async def start(self):
        """Scrapy 2.13+ 的真实入口。"""
        for u in self._entry_urls():
            yield scrapy.Request(u, callback=self.parse_list, dont_filter=True)

    def start_requests(self):
        """兼容旧式入口。"""
        for u in self._entry_urls():
            yield scrapy.Request(u, callback=self.parse_list, dont_filter=True)

    # --- 列表解析 ---------------------------------------------------------

    def parse_list(self, response):
        if self._guard():
            return
        self.session.requests += 1

        # 非 200 由中间件/错误回调处理
        if response.status != 200:
            self.sampler.save_failure(response.url, response.status, response.text,
                                      label="list")
            self.session.request_stop("list_fetch_failed")
            return

        parsed = self.adapter.parse_list(response.text, base_url=response.url)
        if not parsed.descending:
            self.session.request_stop("list_not_descending")
            return

        # 倒序兜底：本页最旧时间早于窗口起点则停止
        oldest = self._oldest_list_time(parsed)
        if oldest is not None and oldest < self.session.window.start_cst:
            self.session.request_stop("window_start_reached")
            return

        for item in parsed.items:
            if self._guard():
                return
            nh = url_hash(item.url)
            # consider 返回 False 表示已抓过（布隆/库内去重），跳过 HTTP 请求
            if not self.session.consider(item.url, nh, list_title=item.title):
                continue
            yield response.follow(item.url, callback=self.parse_detail,
                                  cb_kwargs={"url_hash": nh},
                                  errback=self.on_error)

        # 翻页
        if parsed.next_url and not self._guard():
            nxt = normalize_url(parsed.next_url)
            if nxt not in self._visited_pages:
                self._visited_pages.add(nxt)
                yield response.follow(parsed.next_url, callback=self.parse_list)

    def _oldest_list_time(self, parsed):
        import re

        dates = []
        pat = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")
        from datetime import datetime

        for it in parsed.items:
            m = pat.search(it.list_time_text or "")
            if m:
                try:
                    dates.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
                except ValueError:
                    pass
        return min(dates) if dates else None

    # --- 详情解析 ---------------------------------------------------------

    def parse_detail(self, response, *, url_hash):
        if self._guard():
            return
        self.session.requests += 1

        if response.status in (404, 410):
            self.session.mark_task(url_hash, "skipped", skip_reason=f"http_{response.status}")
            return
        if response.status != 200:
            self.session.mark_task(url_hash, "failed", failure_class="fetch")
            return

        url = response.url
        if is_non_text_page(url, response.text):
            self.session.mark_task(url_hash, "skipped", skip_reason="non_text")
            return

        # 纯 JS 跳转壳页：跟随真实稿件地址再解析一次（只跳一层）
        target = js_redirect_target(response.text)
        if target and not response.meta.get("js_redirected"):
            yield response.follow(
                target, callback=self.parse_detail,
                cb_kwargs={"url_hash": url_hash},
                meta={"js_redirected": True}, errback=self.on_error,
            )
            return

        detail = self.adapter.parse_detail(response.text, url=url)
        parsed = parse_published(detail.published_text, default_year=self.session.window.end_cst.year)
        if parsed.value is not None and parsed.value > self.session.window.end_cst:
            self.session.mark_task(url_hash, "skipped", skip_reason="above_window")
            return

        self._store(detail, url, url_hash, parsed)
        self.session.mark_task(url_hash, "done")

    def _store(self, detail: DetailParse, url: str, nh: str, parsed) -> None:
        paragraphs = clean_paragraphs(detail.paragraphs)
        flags = quality_flags(paragraphs, is_media_only=detail.media_only)
        ch = content_hash(paragraphs)
        # 时间可信度护栏：页脚/版权行、正文引用的历史年份会被误当成发布时间
        # （实测出现过 1956、2610 这类荒谬值），越界即按未知处理。
        # 规则抽到 newsagg/timeguard.py，便于单测与脚本复用。
        cst = clamp_published(parsed.value, self.session.window.end_cst)
        utc = to_utc_naive(cst) if cst else None
        # 详情页标题缺失时，兜底用列表页标题
        title = clean_title(detail.title) or clean_title(self.session.list_title_for(nh))
        self.session.store_detail(
            url=normalize_url(url), url_hash=nh, title=title,
            paragraphs=paragraphs, source_name=clean_source(detail.source_name),
            published_cst=cst, published_utc=utc,
            time_precision=(parsed.precision if cst else "unknown"),
            content_hash=ch, quality_flags=flags,
        )

    # --- 守卫与错误 -------------------------------------------------------

    def _guard(self) -> bool:
        """租约丢失、被封、超预算时返回 True（调用方应停止产出）。"""
        if self.session.should_stop:
            return True
        if self.session.budget_hit():
            return True
        return False

    def on_error(self, failure):
        """请求失败：分类并写样本，不致命则跳过该条。"""
        import scrapy

        url = failure.request.url
        nh = url_hash(url)
        code = "unknown"
        if failure.check(scrapy.spidermiddlewares.httperror.HttpError):
            code = f"http_{failure.value.response.status}"
        elif failure.check(Exception):
            code = type(failure.value).__name__.lower()
        log.info("详情失败 %s: %s", url, code)
        self.session.mark_task(nh, "failed", failure_class=code)
        return None

    def closed(self, reason):
        """蜘蛛关闭：记录停机原因。"""
        log.info(
            "spider 关闭 job=%s reason=%s stop=%s discovered=%s saved=%s",
            self.session.job_id, reason, self.session.stop_reason,
            self.session.discovered, self.session.saved,
        )
        if not self.session.stop_reason:
            self.session.stop_reason = reason


__all__ = ["SiteSpider"]

