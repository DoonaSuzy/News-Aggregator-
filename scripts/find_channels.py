"""栏目页发现：从站点首页/当前栏目页里找同站的其他新闻频道入口。

低产来源往往只爬了一个栏目页（几十条候选就到底）。本脚本列出页面里
"像频道首页"的同站内链（锚文本命中新闻类关键词、或 URL 是目录型索引页），
供人工挑进适配器的 ``extra_column_urls``。

用法::
    python scripts/find_channels.py <adapter> [<adapter> ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.adapters import ensure_loaded, get_adapter  # noqa: E402
from scripts.diagnose_sources import fetch  # noqa: E402

# 频道锚文本关键词
CHANNEL_WORDS = (
    "新闻", "要闻", "时政", "政务", "本地", "本省", "综合", "今日", "焦点",
    "民生", "社会", "经济", "财经", "文化", "教育", "热点", "最新", "排行",
)
# 频道 URL 形态：目录型、索引页
INDEX_HINT = re.compile(r"(/$|/index|/node|/channel|/list|/news/?$|/\d{4}/?$)", re.I)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法: python scripts/find_channels.py <adapter> [...]")
        return 1
    ensure_loaded()
    for name in argv[1:]:
        ad = get_adapter(name)
        status, html = fetch(ad.column_url)
        print(f"\n===== {name}  ({ad.column_url})  HTTP={status}")
        if status != 200:
            continue
        from parsel import Selector

        sel = Selector(text=html)
        seen: set[str] = set()
        hits: list[tuple[str, str]] = []
        for a in sel.css("a"):
            href = a.attrib.get("href", "")
            if not href:
                continue
            text = " ".join(a.css("::text").getall()).strip()
            u = urljoin(ad.column_url, href)
            host = urlsplit(u).netloc.lower()
            if not ad.allows(u):
                continue
            # 只保留同站 + 像频道首页的链接
            by_url = INDEX_HINT.search(u) and not re.search(r"\d{6,}", u)
            by_text = any(w in text for w in CHANNEL_WORDS) and len(text) <= 12
            if not (by_url or by_text):
                continue
            if u in seen:
                continue
            seen.add(u)
            hits.append((u, text))
        for u, t in hits[:24]:
            print(f"  {u[:92]:92s} | {t[:26]}")
        print(f"  （共 {len(hits)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
