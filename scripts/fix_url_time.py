"""URL 日期兜底修复：把 ``articles.published_at_cst`` 为空的记录，
用其 URL 内嵌日期（浙江 ``t20260924_`` 等形态）本地补齐。

零网络请求、零渲染，不依赖详情页是否有时间字样，也不与采集 worker 争抢站点。
对 URL 抽不到日期的记录（如部分湖南/甘肃站）保持不动，交由
``repair_titles.py --scope time`` 走网络/渲染兜底。

用法::

    python scripts/fix_url_time.py --dry-run     # 只看能修多少，不写库
    python scripts/fix_url_time.py --apply       # 实际写库
    python scripts/fix_url_time.py --apply --adapter zhejiang
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.adapters._common import _time_from_url  # noqa: E402
from newsagg.cleaning import to_utc_naive  # noqa: E402
from newsagg.db import Database  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="用 URL 内嵌日期补齐无时间文章")
    ap.add_argument("--apply", action="store_true", help="实际写库（默认 dry-run）")
    ap.add_argument("--adapter", default=None, help="仅处理指定来源")
    args = ap.parse_args(argv)

    db = Database()
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            sql = (
                "SELECT a.id, a.url, s.adapter_name FROM articles a "
                "JOIN sources s ON s.id = a.source_id "
                "WHERE a.published_at_cst IS NULL"
            )
            params: list[object] = []
            if args.adapter:
                sql += " AND s.adapter_name = %s"
                params.append(args.adapter)
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    print(f"待处理（无时间）{len(rows)} 条"
          f"{'（adapter=' + args.adapter + '）' if args.adapter else ''}"
          f"，模式：{'写库' if args.apply else 'dry-run'}")

    fixed = skipped = 0
    fixed_by_src: dict[str, int] = {}
    if args.apply:
        conn = db.connect()
    try:
        for r in rows:
            date_str = _time_from_url(r["url"])
            if not date_str:
                skipped += 1
                continue
            # 日期 → 北京时间 00:00（精度 date），再转 UTC 墙钟
            from datetime import datetime
            cst = datetime.strptime(date_str, "%Y-%m-%d")
            utc = to_utc_naive(cst)
            if args.apply:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE articles SET published_at_utc=%s, published_at_cst=%s, "
                        "time_precision='date', updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                        (utc, cst, r["id"]),
                    )
            fixed += 1
            fixed_by_src[r["adapter_name"]] = fixed_by_src.get(r["adapter_name"], 0) + 1
        if args.apply:
            conn.commit()
    finally:
        if args.apply:
            conn.close()

    print(f"完成：补齐 {fixed} 条，URL 无日期跳过 {skipped} 条")
    if fixed_by_src:
        print("--- 按来源 ---")
        for k, v in sorted(fixed_by_src.items(), key=lambda x: -x[1]):
            print("  ", k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
