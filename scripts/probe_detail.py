"""探查详情页解析质量：直接对 URL 跑适配器 parse_detail。

用法:
    python scripts/probe_detail.py <adapter> <url> [<url> ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.adapters import ensure_loaded, get_adapter  # noqa: E402
from scripts.diagnose_sources import fetch  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("用法: python scripts/probe_detail.py <adapter> <url> [...]")
        return 1
    ensure_loaded()
    ad = get_adapter(argv[1])
    for url in argv[2:]:
        status, html = fetch(url)
        if status != 200:
            print(f"HTTP={status} {url}")
            continue
        d = ad.parse_detail(html, url=url)
        print(f"--- {url}")
        print(f"    title   : {d.title[:80]!r}")
        print(f"    source  : {d.source_name[:40]!r}")
        print(f"    time    : {d.published_text[:40]!r}")
        print(f"    paras   : {len(d.paragraphs)}  首段: {(d.paragraphs[0][:60] if d.paragraphs else '')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
