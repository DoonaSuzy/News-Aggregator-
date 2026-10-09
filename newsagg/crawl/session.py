"""一次抓取任务的运行时状态：租约续期、检查点、候选判定、落库、终态决策。

``CrawlSession`` 把一个站点任务的全部可变状态收拢到一处，
Scrapy 蜘蛛（``crawl/spider.py``）与引擎（``crawl/engine.py``）都通过它
读写。所有 SQL 经 ``newsagg.repo.Repository``，本类不直接写 SQL。

关键行为：
- 租约续期线程：默认 5 分钟租约，每 60 秒续租；令牌失效即停机。
- 候选去重 + 窗口判定：``consider()`` 决定一个详情候选是否入队。
- 阻断：``note_block()`` 命中 403/405/412/429 → 停机 + 冷却。
- 终态：``decide()`` 依据停机原因产出 succeeded / partial / retry_wait。
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

from newsagg.config import get_settings
from newsagg.crawl.dedup import UrlBloom, find_duplicate_article
from newsagg.cleaning import FLAG_DUPLICATE
from newsagg.db import Database
from newsagg.errors import LeaseRejected
from newsagg.logutil import get_logger
from newsagg.repo import Repository
from newsagg.timewindow import Window

log = get_logger()


def _utcnow() -> datetime:
    from newsagg.cleaning import utc_now_naive

    return utc_now_naive()


class CrawlSession:
    """单站点任务的运行时上下文。"""

    def __init__(self, job_id: int, *, source_id: int, window: Window,
                 lease_token: str, owner: str, adapter_name: str,
                 db: Database | None = None, repo: Repository | None = None,
                 bloom: UrlBloom | None = None, refresh: bool = False) -> None:
        self.settings = get_settings()
        self.db = db or Database()
        self.repo = repo or Repository(self.db)

        self.job_id = job_id
        self.source_id = source_id
        self.window = window
        self.lease_token = lease_token
        self.owner = owner
        self.adapter_name = adapter_name

        # URL 布隆过滤器（可选；由 engine 注入 Redis 客户端构造）
        self.bloom = bloom
        #: 修复模式：True 时不跳过已发现的候选，强制重抓以修复元数据
        self.refresh = refresh


        # 计数器与运行态
        self.discovered = 0
        self.saved = 0
        self.requests = 0
        self.checkpoint_cst: datetime | None = None
        self.stop_reason: str | None = None
        self.blocked_status: int | None = None
        self._seen_hashes: set[str] = set()
        #: 列表页标题缓存：url_hash → 列表标题（详情页标题缺失时兜底）
        self._list_titles: dict[str, str] = {}
        self._stop = threading.Event()

        # 租约续期
        self._renew_thread: threading.Thread | None = None
        self._renew_stop = threading.Event()

    # --- 停机信号 ---------------------------------------------------------

    def request_stop(self, reason: str) -> None:
        """请求停止（蜘蛛在下一个 ``_guard`` 检查点关闭）。"""
        if not self.stop_reason:
            self.stop_reason = reason
        self._stop.set()

    @property
    def should_stop(self) -> bool:
        return self._stop.is_set()

    # --- 预算守卫 ---------------------------------------------------------

    def budget_hit(self) -> bool:
        """检查文章/请求预算。返回是否应停止。"""
        if self.saved >= self.settings.max_articles_per_job:
            self.request_stop("article_budget")
        elif self.requests >= self.settings.max_requests_per_job:
            self.request_stop("request_budget")
        return self.should_stop

    # --- 租约续期线程 -----------------------------------------------------

    def start_renewal(self) -> None:
        self._renew_stop.clear()
        self._renew_thread = threading.Thread(target=self._renew_loop, daemon=True)
        self._renew_thread.start()

    def stop_renewal(self) -> None:
        self._renew_stop.set()
        if self._renew_thread:
            self._renew_thread.join(timeout=2)

    def _renew_loop(self) -> None:
        interval = self.settings.lease_renew_seconds
        while not self._renew_stop.wait(interval):
            conn = self.db.connect()
            try:
                ok = self.repo.renew_lease(
                    conn, source_id=self.source_id, token=self.lease_token,
                    lease_seconds=self.settings.lease_seconds,
                )
                conn.commit()
            finally:
                conn.close()
            if not ok:
                log.warning("job %s 租约令牌失效，停机", self.job_id)
                self.request_stop("lease_lost")
                raise LeaseRejected("租约令牌失效")

    # --- 候选判定 ---------------------------------------------------------

    def consider(self, url: str, url_hash: str, *, list_title: str = "") -> bool:
        """判定一个列表候选是否应抓详情。首次见到返回 True。

        ``list_title`` 为列表页标题，缓存用于详情页标题缺失时兜底。
        """
        if list_title:
            self._list_titles[url_hash] = list_title
        if url_hash in self._seen_hashes:
            return False
        self._seen_hashes.add(url_hash)
        self.discovered += 1
        # 修复模式：强制重抓已发现的候选（跳过布隆），让 save_article 修复元数据
        if self.refresh:
            conn = self.db.connect()
            try:
                self.repo.upsert_discovered(
                    conn, source_id=self.source_id, job_id=self.job_id,
                    url_hash=url_hash, url=url,
                )
                conn.commit()
            finally:
                conn.close()
            return True
        # 布隆快速判重：已完整抓取过的 URL 直接跳过 HTTP 请求
        # （误判仅多跳一次 DB 唯一键兜底，不会漏抓新文；真正的去重仍由 DB 保证）
        if self.bloom is not None:
            try:
                if self.bloom.maybe_seen(url_hash):
                    return False
            except Exception:  # noqa: BLE001
                pass
        conn = self.db.connect()
        try:
            new = self.repo.upsert_discovered(
                conn, source_id=self.source_id, job_id=self.job_id,
                url_hash=url_hash, url=url,
            )
            conn.commit()
        finally:
            conn.close()
        return new

    def list_title_for(self, url_hash: str) -> str:
        """返回缓存里的列表标题（详情页标题缺失时的兜底）。"""
        return self._list_titles.get(url_hash, "")

    # --- 阻断策略 ---------------------------------------------------------

    def note_block(self, url: str, status: int) -> None:
        """命中阻断状态码：记录并停机 + 冷却。"""
        self.blocked_status = status
        self.request_stop(f"http_{status}")
        self.apply_block_policy()

    def apply_block_policy(self) -> None:
        """对来源设置冷却（默认 60 分钟）。"""
        if self.blocked_status is None:
            return
        until = _utcnow() + timedelta(minutes=60)
        conn = self.db.connect()
        try:
            self.repo.set_cooldown(conn, self.source_id, until)
            conn.commit()
        finally:
            conn.close()

    # --- 终态决策 ---------------------------------------------------------

    def decide(self) -> tuple[str, int]:
        """依据停机原因产出 (status, retry_minutes)。

        - 无原因或正常发现结束 → succeeded
        - 预算/部分保存 → partial
        - 阻断/取列表失败 → retry_wait（默认 30 分钟后）
        """
        reason = self.stop_reason
        if reason is None or reason == "window_start_reached":
            return "succeeded", 0
        if reason in ("article_budget", "request_budget", "time_budget"):
            return "partial", 0
        if reason == "lease_lost":
            return "retry_wait", 5
        if reason.startswith("http_") or reason == "list_fetch_failed":
            return "retry_wait", 30
        if reason == "list_not_descending":
            return "partial", 0
        return "partial", 0

    # --- 详情落库 ---------------------------------------------------------

    def store_detail(self, *, url: str, url_hash: str, title: str,
                     paragraphs: list[str], source_name: str,
                     published_cst: datetime | None, published_utc: datetime | None,
                     time_precision: str, content_hash: str,
                     quality_flags: list[str]) -> str:
        """写文章 + 更新检查点。返回 upsert outcome。

        多源同文：跨来源按 ``content_hash`` 查到首发文章时，在 ``quality_flags``
        打 ``duplicate_of:<adapter>`` 标记（保留记录不删除）。
        """
        flags = list(quality_flags or [])
        conn = self.db.connect()
        try:
            if content_hash and FLAG_DUPLICATE not in flags:
                dup = find_duplicate_article(
                    conn, source_id=self.source_id, content_hash=content_hash,
                )
                if dup and dup.get("adapter_name"):
                    tag = f"duplicate_of:{dup['adapter_name']}"
                    if tag not in flags:
                        flags.append(tag)
            result = self.repo.save_article(
                conn, source_id=self.source_id, url_hash=url_hash, url=url,
                title=title, body_text="\n".join(paragraphs),
                source_name=source_name, published_utc=published_utc,
                published_cst=published_cst, time_precision=time_precision,
                content_hash=content_hash, quality_flags=flags,
            )
            conn.commit()
        finally:
            conn.close()
        if result.outcome in ("saved", "updated"):
            self.saved += 1
            # 抓取成功后登记到布隆过滤器，供后续批次跳过
            if self.bloom is not None:
                try:
                    self.bloom.add(url_hash)
                except Exception:  # noqa: BLE001
                    pass
        if published_cst and (
            self.checkpoint_cst is None or published_cst < self.checkpoint_cst
        ):
            self.checkpoint_cst = published_cst
        return result.outcome

    def mark_task(self, url_hash: str, status: str, *, skip_reason=None,
                  failure_class=None) -> None:
        conn = self.db.connect()
        try:
            self.repo.mark_task(
                conn, source_id=self.source_id, url_hash=url_hash, status=status,
                skip_reason=skip_reason, failure_class=failure_class,
            )
            conn.commit()
        finally:
            conn.close()

    def fail_task(self, retry_minutes: int) -> None:
        """任务置为重试等待。"""
        conn = self.db.connect()
        try:
            self.repo.set_retry(
                conn, job_id=self.job_id, retry_minutes=retry_minutes,
                stop_reason=self.stop_reason,
            )
            conn.commit()
        finally:
            conn.close()

    def finish(self, status: str) -> None:
        """提交终态、计数、检查点、尝试结果。"""
        conn = self.db.connect()
        try:
            self.repo.finish_job(
                conn, job_id=self.job_id, status=status,
                discovered=self.discovered, saved=self.saved,
                checkpoint_cst=self.checkpoint_cst, stop_reason=self.stop_reason,
                advance_discovery=(status in ("succeeded", "partial")),
            )
            conn.commit()
        finally:
            conn.close()


__all__ = ["CrawlSession"]

