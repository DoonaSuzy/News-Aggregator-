"""统计：全局概览 + 逐来源状态渲染。"""

from __future__ import annotations

from datetime import datetime

from newsagg.db import Database
from newsagg.query import flags_text, format_cst
from newsagg.repo import Repository


def collect_stats(conn, repo: Repository) -> dict:
    """采集统计：全局计数 + 逐来源明细。"""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM sources WHERE verification_status='enabled'")
        enabled = int(cur.fetchone()["n"])

        cur.execute("SELECT COUNT(*) AS n FROM articles")
        total = int(cur.fetchone()["n"])

        cur.execute(
            "SELECT COUNT(*) AS n FROM articles "
            "WHERE CHAR_LENGTH(body_text) > 0"
        )
        with_body = int(cur.fetchone()["n"])

        cur.execute("SELECT COUNT(*) AS n FROM articles WHERE time_precision != 'unknown'")
        with_date = int(cur.fetchone()["n"])

        # 五字段完整：标题/正文/来源/发布/精确时间精度
        cur.execute(
            "SELECT COUNT(*) AS n FROM articles "
            "WHERE title != '' AND CHAR_LENGTH(body_text) > 0 AND source_name != '' "
            "AND published_at_cst IS NOT NULL AND time_precision IN ('minute','second')"
        )
        complete = int(cur.fetchone()["n"])

        cur.execute("SELECT COUNT(*) AS n FROM article_tasks WHERE status='pending'")
        pending = int(cur.fetchone()["n"])

        # 逐来源明细
        cur.execute(
            "SELECT s.adapter_name, s.media_name, s.verification_status, "
            "s.pause_reason, s.cooldown_until_utc, "
            "(SELECT COUNT(*) FROM articles a WHERE a.source_id = s.id) AS articles, "
            "(SELECT MAX(j.updated_at) FROM crawl_jobs j WHERE j.source_id = s.id "
            "  AND j.status IN ('succeeded','partial')) AS last_success, "
            "(SELECT j.stop_reason FROM crawl_jobs j WHERE j.source_id = s.id "
            "  ORDER BY j.updated_at DESC LIMIT 1) AS last_stop "
            "FROM sources s ORDER BY s.province_code, s.adapter_name"
        )
        per_source = cur.fetchall()

    complete_rate = (complete / with_body) if with_body else 0.0
    return {
        "enabled": enabled,
        "total": total,
        "with_body": with_body,
        "with_date": with_date,
        "complete": complete,
        "complete_rate": complete_rate,
        "pending": pending,
        "per_source": per_source,
    }


def render_stats(stats: dict) -> str:
    """把统计渲染为多行文本。"""
    lines = [
        "=== 采集概览 ===",
        f"启用来源数: {stats['enabled']}",
        f"文章总数: {stats['total']}",
        f"正文有效: {stats['with_body']}",
        f"日期确认: {stats['with_date']}",
        f"五字段完整: {stats['complete']}",
        f"完整率: {stats['complete_rate']:.1%}",
        f"待处理积压: {stats['pending']}",
        "",
        "--- 逐来源 ---",
    ]
    for row in stats["per_source"]:
        status = row["verification_status"]
        reason = row["pause_reason"] or ""
        if row["cooldown_until_utc"]:
            reason = f"冷却至 {format_cst(row['cooldown_until_utc'])}"
        stop = row["last_stop"] or "-"
        last = format_cst(row["last_success"]) or "-"
        lines.append(
            f"[{row['adapter_name']}] {row['media_name']} | 状态={status}"
            f" | 文章={row['articles']} | 最近成功={last} | 停止原因={stop}"
            + (f" | {reason}" if reason else "")
        )
    return "\n".join(lines)


def show_stats(*, db: Database | None = None) -> str:
    """一次性连接执行统计并渲染。"""
    repo = Repository(db)
    conn = repo.db.connect()
    try:
        return render_stats(collect_stats(conn, repo))
    finally:
        conn.close()


__all__ = ["collect_stats", "render_stats", "show_stats"]
