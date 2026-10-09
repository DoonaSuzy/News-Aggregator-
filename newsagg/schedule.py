"""调度：每小时协调器建批 + 分发到 Redis Stream。

与设计文档 §2.2 对齐，职责边界：
- ``run_coordinator()``：用 MySQL ``GET_LOCK('newsagg_coordinator')`` 保证
  同一小时只建一次批（幂等）。
- ``schedule_source()``：为单个来源生成或复用一条 ``crawl_jobs``。
- ``publish_jobs()``：用 ``GET_LOCK('newsagg_publish')`` 投递 ``job_id`` 到 Redis。
- ``create_manual_job()``：供手动 ``recrawl`` 命令使用。

全部 SQL 经 ``newsagg.repo.Repository``，本模块不直接写 SQL。
"""

from __future__ import annotations

import socket
import uuid
from datetime import datetime

from newsagg.config import get_settings
from newsagg.db import Database
from newsagg.logutil import get_logger
from newsagg.queue import StreamQueue
from newsagg.repo import Repository
from newsagg.timewindow import build_window, hourly_trigger_key

log = get_logger()

COORDINATOR_LOCK = "newsagg_coordinator"
PUBLISH_LOCK = "newsagg_publish"
#: GET_LOCK 等待超时（秒）
LOCK_TIMEOUT = 5


def owner_id() -> str:
    """当前 worker 身份。"""
    override = __import__("os").environ.get("NEWSAGG_OWNER")
    if override:
        return override
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


def _get_lock(conn, name: str, timeout: int = LOCK_TIMEOUT) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK(%s, %s) AS got", (name, timeout))
        row = cur.fetchone()
    return bool(row and row["got"])


def _release_lock(conn, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT RELEASE_LOCK(%s)", (name,))


def schedule_source(
    conn,
    repo: Repository,
    *,
    source_id: int,
    last_discovery_success_at_utc: datetime | None,
    now_utc: datetime,
) -> int | None:
    """为单个来源生成或复用一条 crawl_jobs，返回新建的 job_id。

    幂等：同一 trigger_key 下已存在则不重复创建（返回 None）。
    """
    trigger = hourly_trigger_key(now_utc)
    done_today = repo.today_done_count(conn, source_id, now_utc)
    first_today = done_today == 0
    window = build_window(
        now_utc,
        last_discovery_success_at_utc=last_discovery_success_at_utc,
        first_today=first_today,
    )
    return repo.create_job(
        conn,
        source_id=source_id,
        trigger_key=trigger,
        job_type=window.job_type,
        window_start_cst=window.start_cst,
        window_end_cst=window.end_cst,
    )


def run_coordinator(now_utc: datetime | None = None, *, force: bool = False) -> dict[str, int]:
    """每小时建批：为每个启用来源生成任务并投递 Redis。

    用 ``GET_LOCK('newsagg_coordinator')`` 保证同一小时只建一次批。
    ``force=True`` 时不检查同小时幂等（用于手动 jobs/coordinator 命令）。
    返回统计信息。
    """
    now = now_utc or datetime.utcnow()
    trigger = hourly_trigger_key(now)
    db = Database()
    conn = db.connect()
    run_id: int | None = None
    job_ids: list[int] = []
    got_lock = False
    try:
        if not force and not _get_lock(conn, COORDINATOR_LOCK):
            log.info("coordinator: 未取得 %s（同小时已在建批）", COORDINATOR_LOCK)
            return {"run_id": 0, "jobs_created": 0, "jobs_dispatched": 0, "trigger": trigger}
        got_lock = True

        repo = Repository(db)
        # 幂等建批：同小时键已有则直接返回
        run_id = repo.insert_run(conn, trigger)
        if run_id is None:
            log.info("coordinator: 触发键 %s 已建批，跳过", trigger)
            return {"run_id": 0, "jobs_created": 0, "jobs_dispatched": 0, "trigger": trigger}

        for slot in repo.list_enabled_slots(conn):
            source_id = int(slot["id"])
            job_id = schedule_source(
                conn, repo,
                source_id=source_id,
                last_discovery_success_at_utc=slot.get("last_discovery_success_at_utc"),
                now_utc=now,
            )
            if job_id:
                job_ids.append(job_id)

        repo.finish_run(conn, run_id, len(job_ids))
        conn.commit()
    finally:
        if got_lock:
            try:
                _release_lock(conn, COORDINATOR_LOCK)
            except Exception:  # noqa: BLE001
                pass
        conn.close()

    dispatched = publish_jobs(job_ids, {"trigger": trigger})
    return {
        "run_id": run_id or 0,
        "jobs_created": len(job_ids),
        "jobs_dispatched": dispatched,
        "trigger": trigger,
    }


def publish_jobs(job_ids: list[int], payload: dict | None = None) -> int:
    """把 job_id 投递到 Redis Stream。返回投递条数。"""
    if not job_ids:
        return 0
    queue = StreamQueue()
    queue.ensure_group()
    count = 0
    for jid in job_ids:
        queue.publish(jid, payload or {})
        count += 1
    return count


def create_manual_job(adapter_name: str, *, days: int = 7) -> int:
    """手动重抓：按天数构造 manual_recrawl 任务并投递，返回 job_id。"""
    from datetime import timedelta

    from newsagg.cleaning import to_cst_naive
    from newsagg.timewindow import JOB_FULL_RESCAN

    now_utc = datetime.utcnow()
    now_cst = to_cst_naive(now_utc)
    start_cst = (now_cst - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    trigger = f"manual{now_cst.strftime('%Y%m%d%H%M%S')}"

    db = Database()
    repo = Repository(db)
    conn = db.connect()
    try:
        src = repo.get_source(conn, adapter_name=adapter_name)
        if not src:
            raise ValueError(f"未找到来源: {adapter_name}")
        job_id = repo.create_job(
            conn,
            source_id=src.id,
            trigger_key=trigger,
            job_type=JOB_FULL_RESCAN,
            window_start_cst=start_cst,
            window_end_cst=now_cst,
        )
        conn.commit()
    finally:
        conn.close()

    if not job_id:
        raise RuntimeError(f"手动任务创建失败（可能重复）: {adapter_name}")
    publish_jobs([job_id], {"trigger": trigger, "manual": True})
    return job_id


__all__ = [
    "run_coordinator",
    "schedule_source",
    "publish_jobs",
    "create_manual_job",
    "owner_id",
    "COORDINATOR_LOCK",
    "PUBLISH_LOCK",
]

