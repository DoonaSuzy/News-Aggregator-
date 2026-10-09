"""手工建批：为全部（或指定）来源建任务并投递 Redis Stream。

协调器 ``run_coordinator`` 只处理 ``source_slots`` 里已启用的一省一槽，
天津/湖北/甘肃这类与同省槽位冲突的候选来源永远排不到任务；本脚本绕过
槽位限制，直接按 adapter 建 manual 任务并投递，供 worker 消费。

用法::
    python scripts/run_batch.py                  # 全部来源建一批
    python scripts/run_batch.py --days 30
    python scripts/run_batch.py --sources hunan henan
    python scripts/run_batch.py --no-publish     # 只建任务不投递
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.cleaning import to_cst_naive  # noqa: E402
from newsagg.db import Database  # noqa: E402
from newsagg.repo import Repository  # noqa: E402
from newsagg.schedule import publish_jobs  # noqa: E402
from newsagg.timewindow import JOB_FULL_RESCAN  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="手工建批并投递")
    ap.add_argument("--days", type=int, default=30, help="回看天数（默认 30）")
    ap.add_argument("--sources", nargs="*", default=None, help="只处理指定 adapter")
    ap.add_argument("--no-publish", action="store_true", help="只建任务不投递")
    args = ap.parse_args(argv)

    now_utc = datetime.utcnow()
    now_cst = to_cst_naive(now_utc)
    start_cst = (now_cst - timedelta(days=args.days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    trigger = f"b{now_cst.strftime('%Y%m%d%H%M%S')}"

    db = Database()
    repo = Repository(db)
    conn = db.connect()
    job_ids: list[int] = []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, adapter_name FROM sources ORDER BY id")
            rows = cur.fetchall()
        for r in rows:
            name = r["adapter_name"]
            if args.sources and name not in args.sources:
                continue
            job_id = repo.create_job(
                conn, source_id=int(r["id"]), trigger_key=trigger,
                job_type=JOB_FULL_RESCAN, window_start_cst=start_cst,
                window_end_cst=now_cst,
            )
            if job_id:
                job_ids.append(job_id)
        conn.commit()
    finally:
        conn.close()

    print(f"trigger={trigger} 窗口 {start_cst} ~ {now_cst}")
    print(f"建任务 {len(job_ids)} 条")
    if not args.no_publish and job_ids:
        n = publish_jobs(job_ids, {"trigger": trigger, "manual": True})
        print(f"投递 {n} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
