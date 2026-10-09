"""把适配器的 column_url / media_name 同步回 sources 表。

适配器改栏目页（如北京改 https 根域、广西改 news 子域、西藏改 xzxw）后，
库里的 ``sources.column_url`` 仍是旧值，引擎优先用库内值，必须同步。

用法:
    python scripts/sync_sources.py          # 打印差异
    python scripts/sync_sources.py --apply  # 落库
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.adapters import ensure_loaded, get_adapter  # noqa: E402
from newsagg.db import Database  # noqa: E402


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    ensure_loaded()
    db = Database()
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, adapter_name, column_url FROM sources")
            rows = cur.fetchall()
        changed = 0
        for r in rows:
            try:
                ad = get_adapter(r["adapter_name"])
            except KeyError:
                continue
            if ad.column_url and ad.column_url != r["column_url"]:
                print(f"{r['adapter_name']:12s} {r['column_url']}"
                      f"  ->  {ad.column_url}")
                changed += 1
                if apply:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE sources SET column_url=%s WHERE id=%s",
                            (ad.column_url, r["id"]),
                        )
        if apply:
            conn.commit()
        print(f"差异 {changed} 处" + ("（已写入）" if apply else "（未写入，加 --apply 生效）"))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
