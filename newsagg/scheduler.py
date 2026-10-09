"""调度器：建批、分发、按租约认领。

每省最多 1 个启用来源 → 单条启用槽，避免重叠。整点触发，自然日边界。

采用 5 分钟有效期租约替代 Redis lock，用事务断言令牌防止旧令牌改任务；
超租约任务可被其他 worker 接管，但不删除原任务（允许任何时刻重跑）。
"""

from __future__ import annotations

import socket
import uuid
from datetime import datetime

import pymysql

from newsagg import errors
from newsagg.config import get_settings
from newsagg.db import Database
from newsagg.queue import StreamQueue
from newsagg.timewindow import Window, build_window, hourly_trigger_key


def owner_id() -> str:
    """当前 worker 身份。"""
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


class Scheduler:
    def __init__(self, db: Database | None = None, queue: StreamQueue | None = None) -> None:
        self.db = db or Database()
        self.queue = queue or StreamQueue()
        self.settings = get_settings()

    def _now_utc(self) -> datetime:
        return datetime.utcnow()

    # --- 认领（lease-based） -------------------------------------------

    def claim_job(self, job_id: int, owner: str) -> Window | None:
        """按租约认领一个 queued 任务，返回其窗口。

        成功后写入 attempt + 状态 running + 新令牌/租约。
        已被他人持有有效租约时抛 ``LeaseBusy``；终态抛 ``JobTerminal``。
        """
        token = uuid.uuid4().hex
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT j.status, j.job_type, j.window_start_cst, j.window_end_cst, "
                    "s.lease_owner, s.lease_until_utc "
                    "FROM crawl_jobs j JOIN sources s ON s.id = j.source_id "
                    "WHERE j.id = %s FOR UPDATE",
                    (job_id,),
                )
                job = cur.fetchone()
                if not job:
                    raise errors.NewsAggError(f"任务不存在: {job_id}")

                now = self._now_utc()
                lease_active = (
                    job["lease_until_utc"] is not None
                    and job["lease_until_utc"] > now
                    and bool(job["lease_owner"])
                    and job["lease_owner"] != owner
                )
                if job["status"] in ("succeeded", "partial"):
                    raise errors.JobTerminal("任务已终态")
                if lease_active:
                    raise errors.LeaseBusy("他人持有有效租约")

                cur.execute(
                    "UPDATE crawl_jobs SET status = 'running', "
                    "attempt_count = attempt_count + 1 WHERE id = %s",
                    (job_id,),
                )
                cur.execute(
                    "UPDATE sources SET lease_token = %s, lease_owner = %s, "
                    "lease_until_utc = DATE_ADD(%s, INTERVAL %s SECOND) "
                    "WHERE id = (SELECT source_id FROM crawl_jobs WHERE id = %s)",
                    (token, owner, now, self.settings.lease_seconds, job_id),
                )
                cur.execute(
                    "INSERT INTO job_attempts (job_id, attempt_no, owner) "
                    "SELECT j.id, j.attempt_count, %s FROM crawl_jobs j WHERE j.id = %s "
                    "ON DUPLICATE KEY UPDATE owner = %s",
                    (owner, job_id, owner),
                )
            conn.commit()

            ws, we = job["window_start_cst"], job["window_end_cst"]
            return Window(ws, we, job["job_type"])
        except pymysql.err.OperationalError:
            conn.rollback()
            raise
        finally:
            conn.close()


    # --- 建批 + 分发 ---------------------------------------------------

    def build_and_dispatch(
        self, now_utc: datetime, *, force: bool = False
    ) -> dict[str, int]:
        """为每个启用来源建立任务并分发到 Redis Stream。

        同小时键幂等：同一小时内重复调用只建一次批。
        返回统计信息。
        """
        trigger = hourly_trigger_key(now_utc)
        conn = self.db.connect()
        run_id = None
        job_ids: list[int] = []
        try:
            with conn.cursor() as cur:
                # 幂等建批：同小时键已有则直接返回
                cur.execute(
                    "INSERT IGNORE INTO crawl_runs (trigger_key, job_count) VALUES (%s, 0)",
                    (trigger,),
                )
                if cur.rowcount == 0:
                    conn.commit()
                    return {"run_id": 0, "jobs_created": 0, "jobs_dispatched": 0, "trigger": trigger}
                run_id = cur.lastrowid

                # 取所有启用槽对应的启用来源
                cur.execute(
                    "SELECT s.id, s.adapter_name, s.province_code, "
                    "s.last_discovery_success_at_utc "
                    "FROM source_slots sl JOIN sources s ON s.id = sl.source_id "
                    "WHERE s.verification_status = 'enabled'"
                )
                slots = cur.fetchall()

                for slot in slots:
                    cur.execute(
                        "SELECT last_discovery_success_at_utc, "
                        "  (SELECT COUNT(*) FROM crawl_jobs j WHERE j.source_id = s.id "
                        "     AND j.status IN ('succeeded','partial') "
                        "     AND DATE(CONVERT_TZ(j.updated_at, '+00:00', '+08:00')) "
                        "       = DATE(CONVERT_TZ(%s, '+00:00', '+08:00'))) AS done_today "
                        "FROM sources s WHERE s.id = %s",
                        (now_utc, slot["id"]),
                    )
                    info = cur.fetchone()
                    first_today = not info or (info.get("done_today") or 0) == 0
                    last_succ = info.get("last_discovery_success_at_utc") if info else None

                    window = build_window(
                        now_utc,
                        last_discovery_success_at_utc=last_succ,
                        first_today=first_today,
                    )
                    cur.execute(
                        "INSERT IGNORE INTO crawl_jobs "
                        "(source_id, trigger_key, job_type, status, "
                        "window_start_cst, window_end_cst) "
                        "VALUES (%s, %s, %s, 'queued', %s, %s)",
                        (slot["id"], trigger, window.job_type,
                         window.start_cst, window.end_cst),
                    )
                    if cur.rowcount and cur.lastrowid:
                        job_ids.append(int(cur.lastrowid))

                cur.execute(
                    "UPDATE crawl_runs SET job_count = %s WHERE id = %s",
                    (len(job_ids), run_id),
                )
            conn.commit()
        finally:
            conn.close()

        for jid in job_ids:
            self.queue.publish(jid, {"trigger": trigger})

        return {
            "run_id": run_id or 0,
            "jobs_created": len(job_ids),
            "jobs_dispatched": len(job_ids),
            "trigger": trigger,
        }


__all__ = ["Scheduler", "owner_id"]

