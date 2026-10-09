"""来源名兜底：把 ``articles.source_name`` 为空的记录，回落到来源媒体名。

很多省级站的详情页不写「来源：xxx」（本站自采稿），解析器自然拿不到来源。
此时来源就是采集它的媒体本身，用 ``sources.media_name``（千龙网/中国西藏新闻网…）
补齐既准确又零网络、零渲染。

用法::

    python scripts/fix_media_source.py             # dry-run，只看能补多少
    python scripts/fix_media_source.py --apply     # 实际写库
    python scripts/fix_media_source.py --apply --adapter xizang
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.db import Database  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="无来源文章回落到来源媒体名")
    ap.add_argument("--apply", action="store_true", help="实际写库（默认 dry-run）")
    ap.add_argument("--adapter", default=None, help="仅处理指定来源")
    args = ap.parse_args(argv)

    db = Database()
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            sql = (
                "SELECT a.id, s.adapter_name, s.media_name FROM articles a "
                "JOIN sources s ON s.id = a.source_id "
                "WHERE (a.source_name IS NULL OR a.source_name='') "
                "  AND s.media_name IS NOT NULL AND s.media_name <> ''"
            )
            params: list[object] = []
            if args.adapter:
                sql += " AND s.adapter_name = %s"
                params.append(args.adapter)
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    print(f"待处理（无来源且有媒体名）{len(rows)} 条"
          f"{'（adapter=' + args.adapter + '）' if args.adapter else ''}"
          f"，模式：{'写库' if args.apply else 'dry-run'}")

    fixed_by_src: dict[str, int] = {}
    if args.apply:
        conn = db.connect()
    try:
        for r in rows:
            if args.apply:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE articles SET source_name=%s, "
                        "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                        (r["media_name"], r["id"]),
                    )
            fixed_by_src[r["adapter_name"]] = fixed_by_src.get(r["adapter_name"], 0) + 1
        if args.apply:
            conn.commit()
    finally:
        if args.apply:
            conn.close()

    print(f"完成：补齐 {len(rows)} 条来源")
    if fixed_by_src:
        print("--- 按来源 ---")
        for k, v in sorted(fixed_by_src.items(), key=lambda x: -x[1]):
            print("  ", k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
