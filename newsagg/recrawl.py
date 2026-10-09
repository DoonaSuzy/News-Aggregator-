"""手动重抓：绕过自然日规则，按天数构造 manual_recrawl 任务。"""

from __future__ import annotations

from datetime import datetime, timedelta

from newsagg.cleaning import to_cst_naive
from newsagg.db import Database
from newsagg.queue import StreamQueue
from newsagg.timewindow import JOB_FULL_RESCAN


def manual_recrawl(adapter: str, *, days: int = 7) -> int:
    """为指定来源建 manual_recrawl 任务并投递，返回 job_id。"""
    now_utc = datetime.utcnow()
    now_cst = to_cst_naive(now_utc)
    start_cst = (now_cst - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    trigger = f"manual{now_cst.strftime('%Y%m%d%H%M%S')}"

    conn = Database().connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM sources WHERE adapter_name = %s", (adapter,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"未找到来源: {adapter}")
            source_id = int(row["id"])
            cur.execute(
                "INSERT INTO crawl_jobs "
                "(source_id, trigger_key, job_type, status, window_start_cst, window_end_cst) "
                "VALUES (%s, %s, %s, 'queued', %s, %s)",
                (source_id, trigger, JOB_FULL_RESCAN, start_cst, now_cst),
            )
            job_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    StreamQueue().publish(job_id, {"trigger": trigger, "manual": True})
    return job_id


__all__ = ["manual_recrawl"]
