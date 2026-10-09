"""Worker：消费 Redis Stream，调用站点爬虫。

投递分类：run / wait / ack（见 classify）。并发 worker 由启动器按
NEWSAGG_WORKER_COUNT 拉起。
"""

from __future__ import annotations

import os
import time

from newsagg.classify import Decision, classify_delivery
from newsagg.db import Database
from newsagg.logutil import get_logger
from newsagg.queue import StreamQueue
from newsagg.scheduler import owner_id
from newsagg.sitespider import SiteCrawler

log = get_logger()


def handle_one(queue: StreamQueue, db: Database, owner: str) -> bool:
    """消费并处理一条消息。返回是否处理了实际工作。"""
    messages = queue.read_new(count=1, block_ms=5000)
    if not messages:
        return False
    msg = messages[0]

    # 读取任务快照
    snapshot = _load_snapshot(db, msg.job_id)
    from datetime import datetime
    try:
        decision = classify_delivery(snapshot, now_utc=datetime.utcnow(), owner=owner)
    except Exception:
        # LeaseBusy / NotDue / JobTerminal → 直接 ack（该消息本周期不处理）
        queue.ack(msg.msg_id)
        return False

    if decision == Decision.ACK:
        queue.ack(msg.msg_id)
        return False
    if decision == Decision.WAIT:
        # 不 ack，留在 pending 供后续接管
        return False

    # RUN
    try:
        crawler = SiteCrawler(msg.job_id, db=db)
        stats = crawler.run()
        log.info("job %s done: %s", msg.job_id, stats)
        queue.ack(msg.msg_id)
    except Exception as exc:  # noqa: BLE001
        log.error("job %s failed: %s", msg.job_id, exc)
        _mark_failed(db, msg.job_id)
        queue.ack(msg.msg_id)
    return True


def _load_snapshot(db: Database, job_id: int):
    from newsagg.classify import JobSnapshot

    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT j.status, j.retry_at_utc, s.lease_token, s.lease_owner, "
                "s.lease_until_utc FROM crawl_jobs j JOIN sources s ON s.id = j.source_id "
                "WHERE j.id = %s",
                (job_id,),
            )
            row = cur.fetchone()
        if not row:
            return JobSnapshot(status="failed")
        return JobSnapshot(
            status=row["status"],
            lease_token=row["lease_token"],
            lease_owner=row["lease_owner"],
            lease_until_utc=row["lease_until_utc"],
            retry_at_utc=row["retry_at_utc"],
        )
    finally:
        conn.close()


def _mark_failed(db: Database, job_id: int) -> None:
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE crawl_jobs SET status='failed', "
                "retry_at_utc = DATE_ADD(UTC_TIMESTAMP(), INTERVAL 30 MINUTE), "
                "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (job_id,),
            )
        conn.commit()
    finally:
        conn.close()


def run_worker() -> None:
    """worker 主循环。"""
    queue = StreamQueue()
    queue.ensure_group()
    db = Database()
    owner = owner_id()
    os.environ["NEWSAGG_OWNER"] = owner
    log.info("worker %s 启动", owner)
    # 接管崩溃遗留
    for m in queue.autoclaim(owner):
        queue.ack(m.msg_id)
    try:
        while True:
            worked = handle_one(queue, db, owner)
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        log.info("worker %s 停止", owner)


__all__ = ["run_worker", "handle_one"]
