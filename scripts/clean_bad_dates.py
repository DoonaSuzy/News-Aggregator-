#!/usr/bin/env python3
"""清理不可信的发布时间（历史脏数据）。

背景
----
`newsagg/timeguard.clamp_published()` 是 2026-10-10 才加进采集链路的护栏。
在那之前入库的记录里混进了两类荒谬值：

- **1956 年**：正文写「1956年10月8日，国防部第五研究院成立」，解析器拿不到
  页面发布时间时回退到「正文第一个日期」，整篇被标成 1956；
- **2610 年**：正文只有「10月8日电」（无年份），日期被拼成了 2610-08-06。

这些值按发布时间倒序时会长期占据首页前列，看起来像「最新新闻」。

本脚本**只处理越界值**（< 2000 年 或 > 现在 + 1 天），不做「日期偏早」的猜测性修复——
那些可能是正常的旧稿转载，需要人工判断。

用法::

    python scripts/clean_bad_dates.py                 # 只报告，不改数据（默认）
    python scripts/clean_bad_dates.py --execute       # 真正执行
    python scripts/clean_bad_dates.py --execute --backup-dir ../backups

执行前请先 `mysqldump` 备份；`--execute` 会在事务里改，失败自动回滚。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pymysql

MIN_YEAR = 2000


def connect():
    """按 `NEWSAGG_MYSQL_*` 环境变量连接（与采集层同一套配置）。"""
    return pymysql.connect(
        host=os.environ.get("NEWSAGG_MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("NEWSAGG_MYSQL_PORT", 3306)),
        user=os.environ.get("NEWSAGG_MYSQL_USER", "newsagg"),
        password=os.environ.get("NEWSAGG_MYSQL_PASSWORD", ""),
        database=os.environ.get("NEWSAGG_MYSQL_DATABASE", "newsagg"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def find_bad_rows(conn) -> list[dict]:
    future_limit = datetime.now() + timedelta(days=1)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source_id, title, published_at_cst, time_precision, quality_flags
            FROM articles
            WHERE published_at_cst < %s OR published_at_cst > %s
            ORDER BY published_at_cst
            """,
            (datetime(MIN_YEAR, 1, 1), future_limit),
        )
        return list(cur.fetchall())


def mark(conn, rows: list[dict]) -> int:
    """置空发布时间并打质量标记，返回受影响行数。"""
    changed = 0
    with conn.cursor() as cur:
        for row in rows:
            flags = row.get("quality_flags") or []
            if isinstance(flags, str):
                try:
                    flags = json.loads(flags)
                except json.JSONDecodeError:
                    flags = []
            tag = f"time_implausible:{row['published_at_cst']:%Y-%m-%d}"
            if tag not in flags:
                flags.append(tag)
            cur.execute(
                """
                UPDATE articles
                SET published_at_cst = NULL,
                    published_at_utc = NULL,
                    time_precision = 'unknown',
                    quality_flags = %s
                WHERE id = %s
                """,
                (json.dumps(flags, ensure_ascii=False), row["id"]),
            )
            changed += cur.rowcount
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="清理越界的发布时间")
    parser.add_argument("--execute", action="store_true", help="真正写库（默认只报告）")
    parser.add_argument(
        "--backup-dir",
        default=None,
        help="执行前提示备份目录；仅用于打印提醒，脚本本身不做备份",
    )
    args = parser.parse_args(argv)

    conn = connect()
    try:
        rows = find_bad_rows(conn)
        print(f"发现 {len(rows)} 条越界发布时间")
        for row in rows:
            print(
                f"  id={row['id']:<6} {row['published_at_cst']}  "
                f"{row['time_precision']:<7} {row['title'][:36]}"
            )

        if not rows:
            return 0
        if not args.execute:
            print("\n这是预览。确认后加 --execute 执行；执行前请先 mysqldump 备份。")
            if args.backup_dir:
                print(f"建议备份到：{Path(args.backup_dir).resolve()}")
            return 0

        changed = mark(conn, rows)
        conn.commit()
        print(f"\n已处理 {changed} 条：发布时间置空，time_precision=unknown，已打 quality_flags")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
