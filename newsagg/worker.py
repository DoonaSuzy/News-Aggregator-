"""Worker：消费 Redis Stream，驱动 Scrapy 引擎抓取站点任务。

数据流（与文档 §3 对齐）：
- ``take_assignment()`` 依次读 pending、``autoclaim`` 新消息，经
  ``classify_delivery()`` 判定 run / wait / ack（租约判定全部走 ``repo``）。
- run：在**独立子进程**里跑 ``crawl.engine.run_blocking``。Twisted 反应器
  不可在同一进程重启，所以每个任务一个干净反应器；子进程写终态成功后，
  父进程统一 XACK。
- 同一站点的执行权在 MySQL 租约里（``repo.acquire_lease``），
  Redis 消息在 MySQL 提交成功后才 XACK，重复投递靠唯一键挡住。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime

from newsagg.classify import Decision, JobSnapshot, classify_delivery
from newsagg.db import Database
from newsagg.logutil import get_logger
from newsagg.queue import StreamQueue
from newsagg.repo import Repository
from newsagg.schedule import owner_id

log = get_logger()

#: run-job 子进程超时（秒），单任务墙钟上限
JOB_SUBPROCESS_TIMEOUT = 3600


def _load_snapshot(repo: Repository, conn, job_id: int) -> JobSnapshot:
    """读任务快照供租约判定。"""
    row = repo.find_open_job(conn, job_id)
    if not row:
        return JobSnapshot(status="failed")
    return JobSnapshot(
        status=row.status,
        lease_token=row.lease_token,
        lease_owner=row.lease_owner,
        lease_until_utc=row.lease_until_utc,
        retry_at_utc=row.retry_at_utc,
    )


def _mark_failed(repo: Repository, conn, job_id: int) -> None:
    """异常兜底：任务置 failed 并 30 分钟后重试。"""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE crawl_jobs SET status='failed', "
            "retry_at_utc = DATE_ADD(UTC_TIMESTAMP(), INTERVAL 30 MINUTE), "
            "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (job_id,),
        )
    conn.commit()


def _run_job_subprocess(job_id: int) -> int:
    """在子进程里同步抓取一个任务，返回子进程退出码。"""
    python = sys.executable
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["NEWSAGG_OWNER"] = worker_identity()
    cmd = [python, "-m", "newsagg", "run-job", str(job_id)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=JOB_SUBPROCESS_TIMEOUT, env=env,
        )
    except subprocess.TimeoutExpired:
        log.error("job %s 子进程超时", job_id)
        return 124
    if proc.stdout:
        log.info("job %s stdout: %s", job_id, proc.stdout.strip())
    if proc.returncode != 0:
        log.error("job %s 子进程失败(rc=%s): %s",
                  job_id, proc.returncode, (proc.stderr or "").strip())
    return proc.returncode


def take_assignment(queue: StreamQueue, db: Database, owner: str) -> bool:
    """消费并处理一条消息。返回是否处理了实际工作。"""
    repo = Repository(db)

    # 优先接管崩溃遗留，再读新消息
    messages = queue.read_pending(count=1) or queue.autoclaim(owner, count=1)
    if not messages:
        messages = queue.read_new(count=1, block_ms=5000)
    if not messages:
        return False
    msg = messages[0]

    conn = db.connect()
    try:
        snapshot = _load_snapshot(repo, conn, msg.job_id)
        try:
            decision = classify_delivery(
                snapshot, now_utc=datetime.utcnow(), owner=owner
            )
        except Exception:  # LeaseBusy / NotDue / JobTerminal
            # 本周期不处理：ack 旧消息，避免反复重投
            queue.ack(msg.msg_id)
            return False
    finally:
        conn.close()

    if decision == Decision.ACK:
        queue.ack(msg.msg_id)
        return False
    if decision == Decision.WAIT:
        # 不 ack，留在 pending 供后续接管
        return False

    # RUN：子进程抓取，写终态成功后 ack
    rc = _run_job_subprocess(msg.job_id)
    if rc == 0:
        log.info("job %s done", msg.job_id)
        queue.ack(msg.msg_id)
    else:
        conn = db.connect()
        try:
            _mark_failed(repo, conn, msg.job_id)
        finally:
            conn.close()
        queue.ack(msg.msg_id)
    return True


def worker_identity() -> str:
    """当前 worker 身份：主机名+PID（与 schedule.owner_id 一致）。"""
    return owner_id()


def run_worker() -> None:
    """worker 主循环。"""
    queue = StreamQueue()
    queue.ensure_group()
    db = Database()
    owner = owner_id()
    os.environ["NEWSAGG_OWNER"] = owner
    log.info("worker %s 启动", owner)
    try:
        while True:
            worked = take_assignment(queue, db, owner)
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        log.info("worker %s 停止", owner)


__all__ = ["run_worker", "take_assignment", "worker_identity"]

