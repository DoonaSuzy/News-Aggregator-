"""抓取引擎：取租约开会话、跑蜘蛛、提交结果后 XACK。

``worker.py`` 通过本模块驱动一次站点任务：
- ``open_session()``：取租约并构造 ``CrawlSession``。
- ``run_blocking()``：同步跑一个任务（供 ``crawl-once`` 与 worker 复用）。
- ``conclude()``：写终态后才 ack（由调用方在 run_blocking 内完成）。
- ``runner()``：返回配置好的 ``CrawlerRunner``。
- ``worker_identity()``：主机名+PID。

引擎不写业务 SQL（委托 session/repo），只负责编排生命周期。
"""

from __future__ import annotations

import os
import socket
from typing import Callable

from newsagg.config import get_settings
from newsagg.crawl.session import CrawlSession
from newsagg.crawl.settings import scrapy_settings
from newsagg.crawl.spider import SiteSpider
from newsagg.db import Database
from newsagg.logutil import get_logger
from newsagg.queue import StreamQueue
from newsagg.repo import Repository

log = get_logger()


def worker_identity() -> str:
    """当前 worker 身份：主机名+PID。"""
    override = os.environ.get("NEWSAGG_OWNER")
    if override:
        return override
    return f"{socket.gethostname()}-{os.getpid()}"


def runner(**overrides):
    """返回配置好的 ``CrawlerRunner``。"""
    from scrapy.crawler import CrawlerRunner

    # 复用 scrapy_settings()，屏蔽 Scrapy 自身日志
    return CrawlerRunner(scrapy_settings(**overrides))


def _build_bloom():
    """构造 URL 布隆过滤器（Redis 位图）。Redis 不可用时返回 None（退化为纯 DB 去重）。"""
    from newsagg.crawl.dedup import UrlBloom

    try:
        queue = StreamQueue()
        return UrlBloom(queue.client)
    except Exception as exc:  # noqa: BLE001
        log.warning("布隆过滤器不可用，退化为库内去重: %s", exc)
        return None


def open_session(job_id: int, *, db: Database | None = None,
                 owner: str | None = None, bloom=None,
                 refresh: bool = False) -> CrawlSession:
    """取租约并构造会话。终态/被他人持有时抛出对应异常。"""
    settings = get_settings()
    db = db or Database()
    repo = Repository(db)
    owner = owner or worker_identity()

    if bloom is None:
        bloom = _build_bloom()

    conn = db.connect()
    try:
        claimed = repo.acquire_lease(conn, job_id, owner, lease_seconds=settings.lease_seconds)
        job_row, lease = claimed
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # 取来源元信息
    conn = db.connect()
    try:
        meta = repo.get_job_source_meta(conn, job_id)
    finally:
        conn.close()
    if not meta:
        raise KeyError(f"任务不存在: {job_id}")

    from newsagg.timewindow import Window

    window = Window(job_row.window_start_cst, job_row.window_end_cst, job_row.job_type)
    return CrawlSession(
        job_id, source_id=int(meta["id"]), window=window, lease_token=lease.token,
        owner=owner, adapter_name=meta["adapter_name"], db=db, repo=repo, bloom=bloom,
        refresh=refresh,
    )


def run_blocking(job_id: int, *, db: Database | None = None, owner: str | None = None,
                 refresh: bool = False) -> dict:
    """同步跑一个任务并等待完成，写终态，返回统计。

    每个任务在独立进程内调用本函数（Twisted 反应器不可在同一进程重启），
    队列 XACK 由调用方（父进程 worker）在子进程写终态成功后统一执行。

    ``refresh=True`` 时启用修复模式：强制重抓已发现候选以修复元数据列。
    """
    from scrapy.crawler import CrawlerProcess

    session = open_session(job_id, db=db, owner=owner, refresh=refresh)
    column_url = _column_url(session)

    # CrawlerProcess 自管反应器生命周期（含安装/运行/停止），
    # stop_after_crawl=True 保证抓取结束后 reactor 停止、本函数返回。
    process = CrawlerProcess(scrapy_settings())

    session.start_renewal()
    try:
        # Scrapy 2.13+ 的 crawl() 只接受蜘蛛“类”+ 构造参数，不接受实例。
        process.crawl(SiteSpider, session=session, column_url=column_url)
        process.start(stop_after_crawl=True)
    finally:
        session.stop_renewal()

    return conclude(session)


def conclude(session: CrawlSession) -> dict:
    """写终态并返回统计。XACK 由调用方负责。"""
    status, retry_minutes = session.decide()
    if status == "retry_wait":
        session.fail_task(retry_minutes)
    else:
        session.finish(status)

    stats = {
        "job_id": session.job_id, "status": status, "discovered": session.discovered,
        "saved": session.saved, "requests": session.requests,
        "stop_reason": session.stop_reason,
    }
    log.info("job %s 完成: %s", session.job_id, stats)
    return stats


def _column_url(session: CrawlSession) -> str:
    """取来源栏目 URL（优先库内 column_url，回退适配器默认）。"""
    repo = session.repo
    conn = session.db.connect()
    try:
        src = repo.get_source(conn, source_id=session.source_id)
    finally:
        conn.close()
    if src and src.column_url:
        return src.column_url
    from newsagg.adapters import ensure_loaded, get_adapter

    ensure_loaded()
    return get_adapter(session.adapter_name).column_url


__all__ = [
    "worker_identity",
    "runner",
    "open_session",
    "run_blocking",
    "conclude",
]
