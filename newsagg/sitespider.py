"""核心站点爬虫：被 jobs/tick 调用的可运行入口。

每个站点一条子进程运行本模块。职责：
- robots.txt 分站点决策（贵州忽略）
- UA 伪装 + Autothrottle + 切分翻页（贵州 5s/并发1）
- 列表倒序翻页，命中窗口上界/倒序破坏/预算则停止
- 详情限窗口上界 + 倒序，优先深度
- 失败采样 + 空页结构/尺寸采样
- 预算：文章数 / 请求数 / 墙钟
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime

from newsagg.adapters import ensure_loaded, get_adapter
from newsagg.cleaning import (
    clean_paragraphs,
    clean_source,
    clean_title,
    content_hash,
    parse_published,
    quality_flags,
    to_utc_naive,
)
from newsagg.config import get_settings
from newsagg.db import Database
from newsagg.scheduler import Scheduler
from newsagg.timewindow import Window
from newsagg.urls import normalize_url, url_hash
from newsagg.writer import ArticleRecord, ArticleWriter

# 失败保留预算
FAIL_SAMPLE_PER_RUN = 200

_CN_TIME = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?[ T]?(\d{1,2})?:?(\d{2})?:?(\d{2})?")


class SiteCrawler:
    """单站点同步爬虫（按窗口执行一次抓取）。"""

    def __init__(self, job_id: int, *, db: Database | None = None) -> None:
        self.job_id = job_id
        self.db = db or Database()
        self.settings = get_settings()
        self.writer = ArticleWriter(self.db)
        self.adapter = None
        self.source_id: int = 0
        self.window: Window | None = None
        self.discovered = 0
        self.saved = 0
        self.requests = 0
        self.checkpoint_cst: datetime | None = None
        self.stop_reason: str | None = None
        self._seen_hashes: set[str] = set()

    def run(self) -> dict[str, int]:
        """执行一次抓取，返回统计。异常由调用方置 failed。"""
        from newsagg.crawl.http import HttpClient

        owner = os.environ.get("NEWSAGG_OWNER", "crawler")
        sched = Scheduler(self.db)
        window = sched.claim_job(self.job_id, owner)
        if window is None:
            return {"discovered": 0, "saved": 0, "requests": 0}
        self.window = window

        meta = self._load_source_meta()
        ensure_loaded()
        self.adapter = get_adapter(meta["adapter_name"])
        self.source_id = int(meta["id"])
        column_url = meta["column_url"] or self.adapter.column_url
        interval = getattr(self.adapter, "request_interval", 0.0)

        http = HttpClient(
            user_agent=self.settings.user_agent,
            timeout=self.settings.download_timeout,
            concurrency=self.settings.concurrency,
            interval=interval,
        )
        window_end = window.end_cst
        deadline = time.monotonic() + self.settings.lease_seconds
        try:
            page_url: str | None = column_url
            visited_pages: set[str] = set()
            while page_url and not self._budget_hit(deadline):
                if page_url in visited_pages:
                    break
                visited_pages.add(page_url)
                html = http.get(page_url)
                self.requests += 1
                if html is None:
                    self.stop_reason = "list_fetch_failed"
                    break
                parsed = self.adapter.parse_list(html, base_url=page_url)
                if not parsed.descending:
                    self.stop_reason = "list_not_descending"
                    break
                detail_urls = [it.url for it in parsed.items]
                if detail_urls:
                    self._crawl_details(http, detail_urls, window_end, deadline)
                oldest = self._oldest_list_time(parsed)
                if oldest is not None and self.window and oldest < self.window.start_cst:
                    self.stop_reason = "window_start_reached"
                    break
                page_url = parsed.next_url
        finally:
            http.close()

        self._finalize("partial" if self.stop_reason else "succeeded")
        return {"discovered": self.discovered, "saved": self.saved, "requests": self.requests}


    # --- 详情抓取 ------------------------------------------------------

    def _crawl_details(self, http, urls: list[str], window_end, deadline) -> None:
        for url in urls:
            if self._budget_hit(deadline):
                self.stop_reason = "budget_exhausted"
                return
            nh = url_hash(url)
            if nh in self._seen_hashes:
                continue
            self._seen_hashes.add(nh)
            self.discovered += 1
            self._insert_task(url, nh)

            html = http.get(url)
            self.requests += 1
            if html is None:
                self._mark_task(nh, "failed", failure_class="fetch")
                continue
            detail = self.adapter.parse_detail(html, url=url)
            parsed = parse_published(detail.published_text, default_year=window_end.year)
            if parsed.value is not None and parsed.value > window_end:
                self._mark_task(nh, "skipped", skip_reason="above_window")
                continue
            self._store(detail, url, nh, parsed)
            self._mark_task(nh, "done")

    def _store(self, detail, url: str, nh: str, parsed) -> None:
        paragraphs = clean_paragraphs(detail.paragraphs)
        flags = quality_flags(paragraphs, is_media_only=detail.media_only)
        ch = content_hash(paragraphs)
        cst = parsed.value
        utc = to_utc_naive(cst) if cst else None
        rec = ArticleRecord(
            source_id=self.source_id,
            url_hash=nh,
            url=normalize_url(url),
            title=clean_title(detail.title),
            paragraphs=paragraphs,
            source_name=clean_source(detail.source_name),
            published_utc=utc,
            published_cst=cst,
            time_precision=parsed.precision,
            content_hash=ch,
            quality_flags=flags,
        )
        result = self.writer.upsert(rec)
        if result.outcome in ("saved", "updated"):
            self.saved += 1
        if cst and (self.checkpoint_cst is None or cst < self.checkpoint_cst):
            self.checkpoint_cst = cst

    def _budget_hit(self, deadline: float) -> bool:
        if self.saved >= self.settings.max_articles_per_job:
            self.stop_reason = self.stop_reason or "article_budget"
            return True
        if self.requests >= self.settings.max_requests_per_job:
            self.stop_reason = self.stop_reason or "request_budget"
            return True
        if time.monotonic() > deadline:
            self.stop_reason = self.stop_reason or "time_budget"
            return True
        return False

    def _oldest_list_time(self, parsed) -> datetime | None:
        dates = []
        for it in parsed.items:
            m = _CN_TIME.search(it.list_time_text or "")
            if m:
                try:
                    dates.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
                except ValueError:
                    pass
        return min(dates) if dates else None

    def _load_source_meta(self) -> dict:
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT s.id, s.adapter_name, s.column_url FROM crawl_jobs j "
                    "JOIN sources s ON s.id = j.source_id WHERE j.id = %s",
                    (self.job_id,),
                )
                return cur.fetchone()
        finally:
            conn.close()

    def _insert_task(self, url: str, nh: str) -> None:
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT IGNORE INTO article_tasks "
                    "(source_id, job_id, discovered_url_hash, url) VALUES (%s,%s,%s,%s)",
                    (self.source_id, self.job_id, nh, url),
                )
            conn.commit()
        finally:
            conn.close()

    def _mark_task(self, nh: str, status: str, *, skip_reason=None, failure_class=None) -> None:
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE article_tasks SET status=%s, skip_reason=%s, failure_class=%s "
                    "WHERE source_id=%s AND discovered_url_hash=%s",
                    (status, skip_reason, failure_class, self.source_id, nh),
                )
            conn.commit()
        finally:
            conn.close()

    def _finalize(self, status: str) -> None:
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE crawl_jobs SET status=%s, discovered_count=%s, saved_count=%s, "
                    "checkpoint_cst=%s, stop_reason=%s, updated_at=CURRENT_TIMESTAMP "
                    "WHERE id=%s",
                    (status, self.discovered, self.saved, self.checkpoint_cst,
                     self.stop_reason, self.job_id),
                )
                cur.execute(
                    "UPDATE sources SET last_discovery_success_at_utc=CURRENT_TIMESTAMP "
                    "WHERE id=%s",
                    (self.source_id,),
                )
                cur.execute(
                    "UPDATE job_attempts SET outcome=%s, finished_at_utc=CURRENT_TIMESTAMP "
                    "WHERE job_id=%s AND attempt_no=("
                    "SELECT attempt_count FROM crawl_jobs WHERE id=%s)",
                    (status, self.job_id, self.job_id),
                )
            conn.commit()
        finally:
            conn.close()


__all__ = ["SiteCrawler", "FAIL_SAMPLE_PER_RUN"]

