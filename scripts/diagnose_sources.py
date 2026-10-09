"""零产出来源诊断：抓取栏目页 → 统计候选发现链路各环节的存活数。

用法:
    python scripts/diagnose_sources.py                 # 诊断全部启用来源
    python scripts/diagnose_sources.py beijing hunan   # 只诊断指定来源

输出每来源一行：HTTP 状态 / 字节数 / <a> 总数 / is_article 命中 /
标题合格 / parse_list 产出 / 样例 URL。
"""

from __future__ import annotations

import gzip
import io
import ssl
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.adapters import ensure_loaded, get_adapter  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 20

_CTX = ssl.create_default_context()
_CTX.set_ciphers("DEFAULT:@SECLEVEL=1")


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX) as resp:
            raw = resp.read()
            enc = (resp.headers.get("Content-Encoding") or "").lower()
            if enc == "gzip":
                raw = gzip.decompress(raw)
            elif enc == "deflate":
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            elif enc == "br":
                raw = _brotli(raw)
            charset = "utf-8"
            ctype = resp.headers.get("Content-Type") or ""
            if "charset=" in ctype:
                charset = ctype.split("charset=")[-1].split(";")[0].strip()
            return resp.status, raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception as exc:  # noqa: BLE001
        return -1, f"{type(exc).__name__}: {exc}"


def _brotli(raw: bytes) -> bytes:
    try:
        import brotli  # type: ignore
        return brotli.decompress(raw)
    except Exception:  # noqa: BLE001
        return raw


def diagnose(name: str) -> None:
    try:
        ad = get_adapter(name)
    except KeyError:
        print(f"{name:14s} 适配器未注册")
        return
    status, html = fetch(ad.column_url)
    if status != 200:
        print(f"{name:14s} HTTP={status:<5} bytes=0      err={html[:70]}")
        return
    from parsel import Selector

    sel = Selector(text=html)
    from urllib.parse import urljoin

    from newsagg.adapters._common import _SKIP_HINT

    links = [a.attrib.get("href", "") for a in sel.css("a")]
    links = [h for h in links if h]
    abs_links = [urljoin(ad.column_url, h) for h in links]
    alive = [u for u in abs_links if not _SKIP_HINT.search(u) and ad.is_article(u)]
    parsed = ad.parse_list(html, base_url=ad.column_url)
    sample = parsed.items[0].url if parsed.items else (alive[0] if alive else "")
    print(f"{name:14s} HTTP=200    bytes={len(html):<7} a={len(links):<5} "
          f"article={len(alive):<5} listed={len(parsed.items):<4} "
          f"| {ad.column_url}")
    print(f"{'':14s} 样例: {sample[:110]}")


def main(argv: list[str]) -> int:
    ensure_loaded()
    from newsagg.adapters import available_adapters

    names = argv[1:] or available_adapters()
    for n in names:
        diagnose(n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
