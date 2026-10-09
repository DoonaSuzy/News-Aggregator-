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
    sub.add_parser("check", help="环境自检（数据库/Redis/依赖）")

    p_jobs = sub.add_parser("jobs", help="建批并分发（整点调度入口）")
    p_jobs.add_argument("--force", action="store_true", help="忽略同小时幂等")
    p_jobs.add_argument("--date", default=None, help="目标窗口日期 YYYY-MM-DD（默认昨天）")

    p_coord = sub.add_parser("coordinator", help="协调器：建批并分发（计划任务入口）")
    p_coord.add_argument("--force", action="store_true")

    sub.add_parser("status", help="查看任务/队列概览")
    sub.add_parser("worker", help="常驻单 worker（消费 Stream）")
    sub.add_parser("supervisor", help="监督进程：维持多个 worker，崩溃自动重启")

    p_tick = sub.add_parser("tick", help="调度+消费一轮（供 cron 调用）")
    p_tick.add_argument("--force", action="store_true")

    p_rw = sub.add_parser("run-worker", help="前台运行多个 worker（开发调试）")
    p_rw.add_argument("--workers", type=int, default=None)

    p_rj = sub.add_parser("run-job", help="单任务运行（不消费队列）")
    p_rj.add_argument("job_id", type=int)

    p_co = sub.add_parser("crawl-once", help="同步抓取单个任务并等待完成")
    p_co.add_argument("job_id", type=int)

    p_rc = sub.add_parser("recrawl", help="手动重抓某来源")
    p_rc.add_argument("adapter", help="adapter 名称")
    p_rc.add_argument("--days", type=int, default=7)

    p_exp = sub.add_parser("export", help="导出文章 CSV")
    p_exp.add_argument("--out", default="newsagg_export.csv")

    p_q = sub.add_parser("query", help="检索文章")
    p_q.add_argument("--province", default=None, help="省份代码或名称")
    p_q.add_argument("--date", default=None, help="日期 YYYY-MM-DD（北京时间）")
    p_q.add_argument("--keyword", default=None, help="标题/正文关键词")
    p_q.add_argument("--unknown-time", action="store_true", help="仅日期未确认")
    p_q.add_argument("--limit", type=int, default=20)
    p_q.add_argument("--offset", type=int, default=0)

    p_show = sub.add_parser("show", help="查看文章详情")
    p_show.add_argument("article_id", type=int)

    sub.add_parser("stats", help="采集统计与逐来源状态")

    p_en = sub.add_parser("enable-source", help="启用来源（需库内已有文章）")
    p_en.add_argument("adapter")

    p_rs = sub.add_parser("resume-source", help="恢复来源（清除暂停与冷却）")
    p_rs.add_argument("adapter")

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
        "check": lambda: _cmd_selfcheck(),
        "jobs": lambda: _cmd_jobs(args.force, args.date),
        "coordinator": lambda: _cmd_coordinator(args.force),
        "status": lambda: _cmd_status(),
        "worker": lambda: _cmd_worker(),
        "supervisor": lambda: _cmd_supervisor(),
        "tick": lambda: _cmd_tick(args.force),
        "run-worker": lambda: _cmd_run_worker(args.workers),
        "run-job": lambda: _cmd_run_job(args.job_id),
        "crawl-once": lambda: _cmd_crawl_once(args.job_id),
        "recrawl": lambda: _cmd_recrawl(args.adapter, args.days),
        "export": lambda: _cmd_export(args.out),
        "query": lambda: _cmd_query(args),
        "show": lambda: _cmd_show(args.article_id),
        "stats": lambda: _cmd_stats(),
        "enable-source": lambda: _cmd_enable_source(args.adapter),
        "resume-source": lambda: _cmd_resume_source(args.adapter),
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
    from newsagg.schedule import run_coordinator

    log.info("建批完成: %s", run_coordinator(force=force))
    return 0


def _cmd_coordinator(force: bool) -> int:
    """协调器入口（每小时计划任务调用）。建批 + 分发。

    用 MySQL ``GET_LOCK('newsagg_coordinator')`` 保证同一小时只建一次批。
    """
    from newsagg.schedule import run_coordinator

    result = run_coordinator(force=force)
    log.info("协调完成: %s", result)
    return 0


def _cmd_worker() -> int:
    """常驻单 worker（供 supervisor 作为子进程拉起）。"""
    from newsagg.worker import run_worker

    run_worker()
    return 0


def _cmd_supervisor() -> int:
    from newsagg.supervisor import supervise

    supervise()
    return 0


def _cmd_crawl_once(job_id: int) -> int:
    """同步抓取单个任务并等待完成（不消费队列，直接跑 Scrapy 引擎）。"""
    from newsagg.crawl.engine import run_blocking

    stats = run_blocking(job_id)
    log.info("crawl-once job %s: %s", job_id, stats)
    return 0


def _cmd_query(args) -> int:
    from newsagg.db import Database
    from newsagg.query import ArticleFilter, ArticleQuery, flags_text, format_cst

    flt = ArticleFilter(
        province=args.province, day=args.date, keyword=args.keyword,
        unknown_time=args.unknown_time, limit=args.limit, offset=args.offset,
    )
    q = ArticleQuery()
    conn = Database().connect()
    try:
        rows, total = q.search_articles(conn, flt)
    finally:
        conn.close()
    print(f"命中 {total} 条，本页 {len(rows)} 条：")
    for r in rows:
        print(
            f"[{r['id']}] {r['province_name'] or r['province_code'] or '-'}"
            f" | {r['media_name']} | {format_cst(r['published_at_cst']) or '时间未知'}"
            f" | {r['title']}"
        )
        print(f"    {r['url']} | 质量: {flags_text(r['quality_flags'])}")
    return 0


def _cmd_show(article_id: int) -> int:
    from newsagg.db import Database
    from newsagg.query import ArticleQuery, flags_text, format_cst

    q = ArticleQuery()
    conn = Database().connect()
    try:
        row = q.get_article(conn, article_id)
    finally:
        conn.close()
    if not row:
        log.error("文章不存在: %s", article_id)
        return 1
    print(f"标题: {row['title']}")
    print(f"来源: {row['media_name']} / {row['source_name']}")
    print(f"省份: {row['province_name'] or row['province_code']}")
    print(f"发布: {format_cst(row['published_at_cst'])} (精度 {row['time_precision']})")
    print(f"链接: {row['url']}")
    print(f"质量: {flags_text(row['quality_flags'])}")
    print("--- 正文 ---")
    print(row["body_text"])
    return 0


def _cmd_stats() -> int:
    from newsagg.stats import show_stats

    print(show_stats())
    return 0


def _cmd_enable_source(adapter: str) -> int:
    from newsagg.db import Database
    from newsagg.repo import Repository

    repo = Repository()
    conn = repo.db.connect()
    try:
        ok = repo.enable_source(conn, adapter)
        conn.commit()
    finally:
        conn.close()
    if ok:
        log.info("已启用来源: %s", adapter)
        return 0
    log.error("无法启用 %s：库内暂无该来源文章", adapter)
    return 1


def _cmd_resume_source(adapter: str) -> int:
    from newsagg.db import Database
    from newsagg.repo import Repository

    repo = Repository()
    conn = repo.db.connect()
    try:
        repo.resume_source(conn, adapter)
        conn.commit()
    finally:
        conn.close()
    log.info("已恢复来源: %s", adapter)
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
    from newsagg.schedule import run_coordinator
    from newsagg.worker import take_assignment
    from newsagg.queue import StreamQueue
    from newsagg.db import Database
    from newsagg.schedule import owner_id

    run_coordinator(force=force)
    queue = StreamQueue()
    queue.ensure_group()
    db = Database()
    owner = owner_id()
    for _ in range(2000):
        if not take_assignment(queue, db, owner):
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
    from newsagg.crawl.engine import run_blocking

    log.info("job %s: %s", job_id, run_blocking(job_id))
    return 0


def _cmd_recrawl(adapter: str, days: int) -> int:
    from newsagg.schedule import create_manual_job

    log.info("manual_recrawl 任务已建: job_id=%s", create_manual_job(adapter, days=days))
    return 0


def _cmd_export(out: str) -> int:
    from newsagg.export import export_csv

    log.info("已导出: %s", export_csv(out))
    return 0


def _cmd_serve() -> int:
    from newsagg.config import get_settings
    from newsagg.schedule import run_coordinator
    from newsagg.worker import run_worker
    import multiprocessing as mp

    run_coordinator()
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
