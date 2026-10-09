"""导出某来源栏目页的链接形态，用于确定 article_pattern / allowed_hosts。

用法: python scripts/dump_links.py <adapter> [topN]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.adapters import ensure_loaded, get_adapter  # noqa: E402
from scripts.diagnose_sources import fetch  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法: python scripts/dump_links.py <adapter> [topN]")
        return 1
    ensure_loaded()
    ad = get_adapter(argv[1])
    top = int(argv[2]) if len(argv) > 2 else 40
    status, html = fetch(ad.column_url)
    print(f"HTTP={status} bytes={len(html)}")
    if status != 200:
        return 1
    from parsel import Selector

    sel = Selector(text=html)
    hosts: Counter[str] = Counter()
    rows: list[tuple[str, str]] = []
    for a in sel.css("a"):
        href = a.attrib.get("href", "")
        if not href:
            continue
        u = urljoin(ad.column_url, href)
        title = " ".join(a.css("::text").getall()).strip()
        if len(title) < 6:
            continue
        hosts[urlsplit(u).netloc] += 1
        rows.append((u, title[:40]))
    print("hosts:", hosts.most_common(8))
    art = [(u, t) for u, t in rows if re.search(r"\d{5,}", u)]
    print(f"--- 疑似文章链接（含5位以上数字）前 {top} 条 / 共 {len(art)} ---")
    for u, t in art[:top]:
        print(f"{u[:100]:100s} | {t}")
    # 形态统计
    pats = [
        (r"/\d{4}-\d{2}/\d{2}/", "date-path"),
        (r"/\d{6,}/", "long-digits"),
        (r"content_\d+", "content_N"),
        (r"\d{8,}", "8+digits"),
        (r"\.s?html?$", "html-suffix"),
        (r"/\d{4}/\d{2}/", "yyyy/mm"),
        (r"(news|article|detail|xw|content|system)", "keyword"),
    ]
    print("--- 形态命中 ---")
    for p, label in pats:
        n = sum(1 for u, _ in rows if re.search(p, u, re.I))
        print(f"{label:14s} {n}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
