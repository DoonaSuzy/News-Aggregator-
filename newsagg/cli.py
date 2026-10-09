"""命令行入口。

子命令：init-db / selfcheck / jobs / tick / run-worker / run-job /
recrawl / export / serve / sources。
"""

from __future__ import annotations

import argparse
import sys

from newsagg.logutil import get_logger, setup_logging

log = get_logger()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="newsagg", description="省级新闻聚合爬虫")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="建表并写入省份/来源种子")
    sub.add_parser("selfcheck", help="自检数据库与依赖连通性")

    p_jobs = sub.add_parser("jobs", help="建批并分发（整点调度入口）")
    p_jobs.add_argument("--force", action="store_true", help="忽略同小时幂等")
    p_jobs.add_argument("--date", default=None, help="目标窗口日期 YYYY-MM-DD（默认昨天）")

    sub.add_parser("status", help="查看任务/队列概览")

    p_tick = sub.add_parser("tick", help="调度+消费一轮（供 cron 调用）")
    p_tick.add_argument("--force", action="store_true")

    p_rw = sub.add_parser("run-worker", help="消费 Stream 的常驻 worker")
    p_rw.add_argument("--workers", type=int, default=None)

    p_rj = sub.add_parser("run-job", help="单任务运行（不消费队列）")
    p_rj.add_argument("job_id", type=int)

    p_rc = sub.add_parser("recrawl", help="手动重抓某来源")
    p_rc.add_argument("adapter", help="adapter 名称")
    p_rc.add_argument("--days", type=int, default=7)

    p_exp = sub.add_parser("export", help="导出文章 CSV")
    p_exp.add_argument("--out", default="newsagg_export.csv")

    sub.add_parser("serve", help="前台运行调度器 + worker（开发调试）")
    sub.add_parser("sources", help="列出所有来源与状态")
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        log.error("命令执行失败: %s", exc)
        return 1


def _dispatch(args) -> int:
    cmd = args.command
    table = {
        "init-db": lambda: _cmd_init_db(),
        "selfcheck": lambda: _cmd_selfcheck(),
        "jobs": lambda: _cmd_jobs(args.force, args.date),
        "status": lambda: _cmd_status(),
        "tick": lambda: _cmd_tick(args.force),
        "run-worker": lambda: _cmd_run_worker(args.workers),
        "run-job": lambda: _cmd_run_job(args.job_id),
        "recrawl": lambda: _cmd_recrawl(args.adapter, args.days),
        "export": lambda: _cmd_export(args.out),
        "serve": lambda: _cmd_serve(),
        "sources": lambda: _cmd_sources(),
    }
    fn = table.get(cmd)
    if fn is None:
        return 2
    return fn()


def _cmd_init_db() -> int:
    from newsagg.db import init_database

    r = init_database()
    log.info("初始化完成: 省份+%s 来源+%s", r["provinces_added"], r["sources_added"])
    return 0


def _cmd_selfcheck() -> int:
    from newsagg.db import Database
    from newsagg.queue import StreamQueue

    try:
        log.info("MySQL OK: %s", Database().ping())
    except Exception as exc:  # noqa: BLE001
        log.error("MySQL 连接失败: %s", exc)
        return 1
    try:
        StreamQueue().client.ping()
        log.info("Redis OK")
    except Exception as exc:  # noqa: BLE001
        log.error("Redis 连接失败: %s", exc)
        return 1
    return 0


def _cmd_jobs(force: bool, date: str | None) -> int:
    from datetime import datetime
    from newsagg.scheduler import Scheduler

    now = datetime.utcnow()
    log.info("建批完成: %s", Scheduler().build_and_dispatch(now, force=force))
    return 0


def _cmd_status() -> int:
    from newsagg.db import Database
    from newsagg.queue import StreamQueue

    conn = Database().connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status, COUNT(*) n FROM crawl_jobs GROUP BY status")
            jobs = {r["status"]: r["n"] for r in cur.fetchall()}
            cur.execute("SELECT COUNT(*) n FROM articles")
            articles = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) n FROM sources WHERE verification_status='enabled'")
            enabled = cur.fetchone()["n"]
    finally:
        conn.close()
    pending = StreamQueue().message_pending()["pending"]
    print(f"启用来源: {enabled}")
    print(f"文章总数: {articles}")
    print(f"任务状态: {jobs}")
    print(f"队列 pending: {pending}")
    return 0


def _cmd_tick(force: bool) -> int:
    from datetime import datetime
    from newsagg.scheduler import Scheduler
    from newsagg.worker import handle_one
    from newsagg.queue import StreamQueue
    from newsagg.db import Database
    from newsagg.scheduler import owner_id

    Scheduler().build_and_dispatch(datetime.utcnow(), force=force)
    queue = StreamQueue()
    queue.ensure_group()
    db = Database()
    owner = owner_id()
    for _ in range(2000):
        if not handle_one(queue, db, owner):
            break
    return 0


def _cmd_run_worker(workers: int | None) -> int:
    from newsagg.config import get_settings
    from newsagg.worker import run_worker
    import multiprocessing as mp

    n = workers or get_settings().worker_count
    procs = [mp.Process(target=run_worker, daemon=True) for _ in range(n)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    return 0


def _cmd_run_job(job_id: int) -> int:
    from newsagg.sitespider import SiteCrawler

    log.info("job %s: %s", job_id, SiteCrawler(job_id).run())
    return 0


def _cmd_recrawl(adapter: str, days: int) -> int:
    from newsagg.recrawl import manual_recrawl

    log.info("manual_recrawl 任务已建: job_id=%s", manual_recrawl(adapter, days=days))
    return 0


def _cmd_export(out: str) -> int:
    from newsagg.export import export_csv

    log.info("已导出: %s", export_csv(out))
    return 0


def _cmd_serve() -> int:
    from newsagg.config import get_settings
    from newsagg.scheduler import Scheduler
    from newsagg.worker import run_worker
    from datetime import datetime
    import multiprocessing as mp

    Scheduler().build_and_dispatch(datetime.utcnow())
    procs = [mp.Process(target=run_worker, daemon=True) for _ in range(get_settings().worker_count)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    return 0


def _cmd_sources() -> int:
    from newsagg.db import Database

    conn = Database().connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT adapter_name, media_name, province_code, verification_status, pause_reason "
                "FROM sources ORDER BY province_code"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    print(f"{'adapter':<14}{'媒体':<18}{'省':<6}{'状态':<10}暂停原因")
    for r in rows:
        print(
            f"{r['adapter_name']:<14}{r['media_name']:<18}"
            f"{r['province_code'] or '-':<6}{r['verification_status']:<10}{r['pause_reason'] or ''}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
