"""数据质量报表：按来源统计文章数、空标题、空正文、缺发布时间。

用法::
    python scripts/quality_report.py
    python scripts/quality_report.py --top 10   # 只看问题最多的 N 个来源
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.db import Database  # noqa: E402

SQL = """
SELECT s.adapter_name AS name, COUNT(*) AS tot,
       SUM(a.title IS NULL OR a.title = '') AS bad_t,
       SUM(a.body_text IS NULL OR a.body_text = '') AS bad_b,
       SUM(a.published_at_cst IS NULL) AS bad_p,
       SUM(a.source_name IS NULL OR a.source_name = '') AS bad_s
FROM articles a JOIN sources s ON s.id = a.source_id
GROUP BY s.id
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=0, help="只看问题最多的 N 个来源")
    args = ap.parse_args(argv)

    conn = Database().connect()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL)
            rows = cur.fetchall()
    finally:
        conn.close()

    def bad(r) -> int:
        return int(r["bad_t"]) + int(r["bad_b"]) + int(r["bad_p"])

    if args.top:
        rows = sorted(rows, key=bad, reverse=True)[: args.top]
    else:
        rows = sorted(rows, key=lambda r: -int(r["tot"]))

    print(f"{'来源':<14}{'文章':>6}{'空标题':>7}{'空正文':>7}{'无时间':>7}{'无来源':>7}")
    tot = [0, 0, 0, 0, 0]
    for r in rows:
        print(f"{r['name']:<14}{int(r['tot']):>6}{int(r['bad_t']):>7}"
              f"{int(r['bad_b']):>7}{int(r['bad_p']):>7}{int(r['bad_s']):>7}")
        for i, k in enumerate(("tot", "bad_t", "bad_b", "bad_p", "bad_s")):
            tot[i] += int(r[k])
    print(f"{'合计':<14}{tot[0]:>6}{tot[1]:>7}{tot[2]:>7}{tot[3]:>7}{tot[4]:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
