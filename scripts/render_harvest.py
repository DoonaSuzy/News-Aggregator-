"""渲染采集：给纯 JS 站点补齐候选与正文。

部分省级站点（海南南海网、江苏中国江苏网部分频道、广西广电…）的列表页和
详情页都由 JS 注入，Scrapy 走纯 HTTP 只能拿到模板壳页。本脚本改用 headless
chromium 渲染：

1. 渲染栏目入口页（``column_url`` + ``extra_column_urls``），用适配器自己的
   ``parse_list`` 抽候选（渲染后的 HTML 对 Selector 完全可用）；
   ``parse_list`` 为空时退回「全部 is_article 链接」。
2.渲染每个详情页，用适配器的 ``parse_detail`` 解析（正文容器已知时更准），
   适配器解析不出段落时退回渲染页的全文 ``<p>`` 密度法。
3. 按时间窗口过滤，写 ``articles``（走 ``repo.save_article``，只补不覆盖），
   并在 ``article_tasks`` 里登记候选与列表页标题（便于后续修复模式复用）。

用 playwright 的 asyncio API，天然可并发，不受 greenlet 跨线程限制。

用法::
    python scripts/render_harvest.py --sources hainan jiangsu --days 30
    python scripts/render_harvest.py --sources hainan --limit 20 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.adapters import ensure_loaded, get_adapter  # noqa: E402
from newsagg.cleaning import (  # noqa: E402
    clean_paragraphs, clean_source, clean_title, content_hash,
    parse_published, quality_flags, to_cst_naive, to_utc_naive,
)
from newsagg.db import Database  # noqa: E402
from newsagg.repo import Repository  # noqa: E402
from newsagg.urls import normalize_url, url_hash  # noqa: E402

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_FOOTER_HINT = re.compile(
    r"(版权所有|Copyright|ICP|备案号|主办单位|承办单位|技术支持|友情链接|"
    r"扫一扫|分享到|上一条|下一条|阅读次数|"
    r"modal window|Beginning of dialog|End of dialog|skip to main content)",
    re.I,
)
_BAD_TITLE = re.compile(
    r"(更多资讯|下载.{0,6}客户端|扫码|关注我们|上一篇|下一篇|返回顶部|"
    r"版权所有|Copyright|登录|注册)",
    re.I,
)


async def _render_one(page, url: str, wait_ms: int, timeout: int) -> str:
    await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    try:
        await page.wait_for_load_state("networkidle", timeout=wait_ms)
    except Exception:  # noqa: BLE001
        await page.wait_for_timeout(wait_ms)
    return await page.content()


def _fallback_paragraphs(html: str) -> list[str]:
    """渲染页全文 <p> 密度法（适配器解析不出正文时用）。"""
    from parsel import Selector

    paras: list[str] = []
    for p in Selector(text=html).css("p"):
        text = " ".join(p.css("::text").getall()).strip()
        if len(text) < 15:
            continue
        link_text = "".join(p.css("a::text").getall()).strip()
        if link_text and len(link_text) > len(text) * 0.6:
            continue
        if _FOOTER_HINT.search(text) and len(text) < 80:
            continue
        paras.append(text)
    return paras if sum(len(p) for p in paras) >= 120 else []


async def harvest_source(
    name: str, *, days: int, limit: int, wait_ms: int, concurrency: int,
    dry_run: bool, db: Database, repo: Repository, stats: dict,
) -> None:
    try:
        adapter = get_adapter(name)
    except KeyError:
        print(f"  !! 未注册适配器 {name}")
        return

    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM sources WHERE adapter_name=%s", (name,))
            row = cur.fetchone()
        if not row:
            print(f"  !! sources 表没有 {name}")
            return
        source_id = int(row["id"])
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        start_cst = to_cst_naive(now_utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=days - 1)
        end_cst = to_cst_naive(now_utc)
    finally:
        conn.close()

    entries = [adapter.column_url, *(getattr(adapter, "extra_column_urls", ()) or ())]
    entries = [u for u in entries if u]

    from playwright.async_api import async_playwright

    candidates: dict[str, str] = {}  # url -> list_title
    details: list[tuple[str, str]] = []  # (url, html)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage"],
        )
        sem = asyncio.Semaphore(concurrency)

        async def render(url: str) -> str:
            async with sem:
                ctx = await browser.new_context(user_agent=UA, locale="zh-CN",
                                                viewport={"width": 1280, "height": 900})
                try:
                    page = await ctx.new_page()
                    return await _render_one(page, url, wait_ms, 30000)
                except Exception as exc:  # noqa: BLE001
                    print(f"    渲染失败 {type(exc).__name__} {url[:70]}")
                    return ""
                finally:
                    await ctx.close()

        # 1) 列表页
        for u in entries:
            html = await render(u)
            if not html:
                continue
            parsed = adapter.parse_list(html, base_url=u)
            found = {it.url: (it.title or "") for it in parsed.items}
            if not found:
                from urllib.parse import urljoin

                from parsel import Selector
                for href in Selector(text=html).css("a::attr(href)").getall():
                    full = urljoin(u, href)
                    if adapter.is_article(full):
                        found.setdefault(full, "")
            for url, title in found.items():
                candidates.setdefault(normalize_url(url), title)
            stats["list_pages"] += 1
            print(f"    [{name}] {u} -> 候选 {len(found)}（累计 {len(candidates)}）")

        # 2) 详情页（跳过已有正文的）
        todo: list[str] = []
        for url in candidates:
            nh = url_hash(url)
            conn = db.connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM articles WHERE source_id=%s AND url_hash=%s "
                        "AND body_text IS NOT NULL AND body_text<>'' LIMIT 1",
                        (source_id, nh),
                    )
                    if cur.fetchone():
                        continue
            finally:
                conn.close()
            todo.append(url)
        todo = todo[:limit]
        print(f"    [{name}] 待渲染详情 {len(todo)} 条")

        results = await asyncio.gather(*(render(u) for u in todo))
        details = [(u, h) for u, h in zip(todo, results) if h]
        await browser.close()

    # 3) 解析 + 落库（主线程，避免 greenlet 跨线程）
    saved = updated = skipped = 0
    for url, html in details:
        d = adapter.parse_detail(html, url=url)
        paras = clean_paragraphs(d.paragraphs) or clean_paragraphs(
            _fallback_paragraphs(html)
        )
        title = clean_title(d.title) or clean_title(candidates.get(url, ""))
        if title and (_BAD_TITLE.search(title) or len(title) < 6):
            title = ""
        parsed = parse_published(d.published_text, default_year=end_cst.year)
        cst = parsed.value
        if cst is not None and (cst.year < 2000 or cst > end_cst + timedelta(days=1)):
            cst = None
        if cst is not None and cst < start_cst:
            skipped += 1
            continue
        if not paras:
            skipped += 1
            continue
        utc = to_utc_naive(cst) if cst else None
        nh = url_hash(url)
        flags = quality_flags(paras, is_media_only=False)
        if dry_run:
            print(f"    [dry] {title[:40]!r} paras={len(paras)} {cst}")
            saved += 1
            continue
        conn = db.connect()
        try:
            res = repo.save_article(
                conn, source_id=source_id, url_hash=nh, url=normalize_url(url),
                title=title, body_text="\n".join(paras),
                source_name=clean_source(d.source_name),
                published_utc=utc, published_cst=cst,
                time_precision=(parsed.precision if cst else "unknown"),
                content_hash=content_hash(paras), quality_flags=flags,
            )
            conn.commit()
        finally:
            conn.close()
        if res.outcome == "saved":
            saved += 1
        elif res.outcome == "updated":
            updated += 1
        else:
            skipped += 1

    stats["saved"] += saved
    stats["updated"] += updated
    stats["skipped"] += skipped
    print(f"  [{name}] 渲染详情 {len(details)}：新增 {saved}，更新 {updated}，跳过 {skipped}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--limit", type=int, default=120, help="每来源最多渲染多少详情")
    ap.add_argument("--wait", type=int, default=2500, help="渲染额外等待毫秒")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    ensure_loaded()
    db = Database()
    repo = Repository(db)
    stats = {"list_pages": 0, "saved": 0, "updated": 0, "skipped": 0}

    async def runner():
        for name in args.sources:
            await harvest_source(
                name, days=args.days, limit=args.limit, wait_ms=args.wait,
                concurrency=args.concurrency, dry_run=args.dry_run,
                db=db, repo=repo, stats=stats,
            )

    asyncio.run(runner())
    print(f"合计：列表页 {stats['list_pages']}，新增 {stats['saved']}，"
          f"更新 {stats['updated']}，跳过 {stats['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
