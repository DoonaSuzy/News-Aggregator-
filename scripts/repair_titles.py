"""元数据修复：补回空标题 / 空正文 / 空来源 / 空时间。

历史批次里有一批文章的字段是空的（详情页选择器没命中、站点改版、抓到壳页、
或正文由 JS 注入）。本脚本对这类记录做一次定向修复：

1. 先用 ``article_tasks.list_title``（列表页标题，已在采集时落库）兜底；
2. 仍缺则直连原文 URL 重新解析；
3. 页面是纯 JS 跳转壳（如 world.newssc.org → h.xinhuaxmt.com）时跟随跳转目标；
4. 静态解析仍拿不到正文时，可用无头浏览器渲染（``--render``，救江苏、部分
   视频/图文混排页）；
5. 只填空，不覆盖已有值。

用法::
    python scripts/repair_titles.py                       # 全部来源，最多 2000 条
    python scripts/repair_titles.py --adapter jiangsu --render
    python scripts/repair_titles.py --scope source        # 只补空来源
    python scripts/repair_titles.py --dry-run             # 只看能修多少，不写库
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.adapters import ensure_loaded, get_adapter  # noqa: E402
from newsagg.cleaning import (  # noqa: E402
    clean_paragraphs, clean_source, clean_title, content_hash,
    parse_published, to_utc_naive,
)
from newsagg.db import Database  # noqa: E402

_META_CHARSET = re.compile(rb'<meta[^>]+charset=["\']?\s*([a-zA-Z0-9\-_]+)', re.I)
#: 纯 JS 跳转壳页：<script>location.href = "..."</script>
_JS_REDIRECT = re.compile(
    r"""(?:location\.href|window\.location|location\.replace)\s*=\s*["']([^"']+)["']""",
    re.I,
)
#: 正文里「发布时间」的常见形态
_TIME_IN_TEXT = re.compile(
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

#: 明显不是标题的文案（APP 导流、导航语等），兜底时不能拿来当标题
_BAD_TITLE = re.compile(
    r"(更多资讯|下载.{0,6}客户端|扫码|关注我们|上一篇|下一篇|返回顶部|"
    r"版权所有|Copyright|登录|注册|首页\s*>)",
    re.I,
)

SCOPES = {
    # 说明 -> WHERE 片段
    "body": "(a.title IS NULL OR a.title='' OR a.body_text IS NULL OR a.body_text='')",
    "source": "(a.source_name IS NULL OR a.source_name='')",
    "time": "(a.published_at_cst IS NULL)",
    "all": (
        "(a.title IS NULL OR a.title='' OR a.body_text IS NULL OR a.body_text='' "
        "OR a.source_name IS NULL OR a.source_name='' OR a.published_at_cst IS NULL)"
    ),
}


def decode(raw: bytes, header_charset: str) -> str:
    """按 header / meta charset 解码，中文站常见 gbk。"""
    charset = header_charset
    if not charset:
        m = _META_CHARSET.search(raw[:4096])
        if m:
            charset = m.group(1).decode("ascii", errors="replace")
    for enc in (charset, "utf-8", "gb18030"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _fetch(url: str, timeout: int = 25) -> str:
    """取回解码后的 HTML。"""
    from scripts.diagnose_sources import _CTX

    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type") or ""
        charset = ""
        if "charset=" in ctype:
            charset = ctype.split("charset=")[-1].split(";")[0].strip()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if enc == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        elif enc == "deflate":
            import zlib
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        return decode(raw, charset)


def _render(url: str) -> str | None:
    """无头浏览器渲染，返回渲染后的 HTML；playwright 不可用时返回 None。

    注意：Playwright 的同步 API 依赖 greenlet，**不能跨线程复用**，因此渲染
    只能在主线程里串行跑（见 ``main`` 的第二阶段）。
    """
    try:
        from scripts.render_fetch import render_html_guarded as render_html
    except Exception:  # noqa: BLE001
        return None
    try:
        return render_html(url)
    except Exception:  # noqa: BLE001
        return None


def _follow_js_redirect(html: str, base: str) -> str:
    """壳页里只有 JS 跳转时，跟随目标再取一次。"""
    if len(html) > 4096:
        return html
    m = _JS_REDIRECT.search(html)
    if not m:
        return html
    target = m.group(1).strip()
    if target.startswith("/"):
        from urllib.parse import urljoin
        target = urljoin(base, target)
    if not target.startswith("http"):
        return html
    try:
        return _fetch(target)
    except Exception:  # noqa: BLE001
        return html


def _time_from_text(html: str) -> str | None:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    m = _TIME_IN_TEXT.search(text)
    return m.group(0) if m else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=None, help="只修指定来源")
    ap.add_argument("--scope", default="body", choices=sorted(SCOPES))
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--render", action="store_true",
                    help="静态解析拿不到正文时用无头浏览器再试一次")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    ensure_loaded()
    db = Database()
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            sql = (
                "SELECT a.id, a.url, a.title, a.body_text, a.source_name, "
                "a.published_at_cst, s.adapter_name, "
                "COALESCE(t.list_title, '') AS list_title "
                "FROM articles a JOIN sources s ON s.id = a.source_id "
                "LEFT JOIN article_tasks t ON t.source_id = a.source_id "
                "  AND t.discovered_url_hash = a.url_hash "
                f"WHERE {SCOPES[args.scope]}"
            )
            params: list[object] = []
            if args.adapter:
                sql += " AND s.adapter_name = %s"
                params.append(args.adapter)
            sql += " ORDER BY a.id LIMIT %s"
            params.append(args.limit)
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    print(f"待修复 {len(rows)} 条（scope={args.scope}"
          f"{', adapter=' + args.adapter if args.adapter else ''}"
          f"{', render' if args.render else ''}）")

    def work(r):
        """第一阶段：静态重解析（并发）。返回 (aid, updated, err, needs_render)。"""
        aid = int(r["id"])
        title = r["title"] or ""
        body = r["body_text"] or ""
        src = r["source_name"] or ""
        published = r["published_at_cst"]
        updated: dict[str, object] = {}

        # 1) 列表页标题兜底（不发请求）
        if not title and r["list_title"]:
            cand = clean_title(r["list_title"])
            if cand:
                updated["title"] = cand
                title = cand

        need = (not title or not body or not src or published is None)
        if not need:
            return aid, updated, None, False

        try:
            ad = get_adapter(r["adapter_name"])
        except KeyError:
            return aid, updated, f"无适配器 {r['adapter_name']}", False

        try:
            html = _fetch(r["url"])
            html = _follow_js_redirect(html, r["url"])
            d = ad.parse_detail(html, url=r["url"])
        except Exception:  # noqa: BLE001
            return aid, updated, "fetch", False

        # 静态解析仍无正文 → 交给第二阶段用无头浏览器渲染
        if args.render and not body and not d.paragraphs:
            return aid, updated, None, True

        if not title:
            cand = clean_title(d.title)
            if cand and not _BAD_TITLE.search(cand) and len(cand) >= 6:
                updated["title"] = cand
        if not body:
            paras = clean_paragraphs(d.paragraphs)
            if paras:
                updated["body_text"] = "\n".join(paras)
                updated["content_hash"] = content_hash(paras)
        if not src and d.source_name:
            cand = clean_source(d.source_name)
            if cand:
                updated["source_name"] = cand
        if published is None:
            txt = d.published_text or _time_from_text(html) or ""
            if txt:
                try:
                    parsed = parse_published(txt)
                    if parsed.value is not None:
                        updated["published_at_utc"] = to_utc_naive(parsed.value)
                        updated["published_at_cst"] = parsed.value
                        updated["time_precision"] = parsed.precision
                except Exception:  # noqa: BLE001
                    pass
        time.sleep(args.sleep)
        return aid, updated, None, False

    def persist(aid, updated):
        """写库并累计统计（非 dry-run 时）。"""
        nonlocal fixed_title, fixed_body, fixed_src, fixed_time
        if "title" in updated:
            fixed_title += 1
        if "body_text" in updated:
            fixed_body += 1
        if "source_name" in updated:
            fixed_src += 1
        if "published_at_cst" in updated:
            fixed_time += 1
        if args.dry_run:
            print(f"  [dry] #{aid} {list(updated)} {str(updated.get('title'))[:36]!r}")
            return
        sets = ", ".join(f"{k}=%s" for k in updated)
        conn = db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE articles SET {sets}, updated_at=CURRENT_TIMESTAMP "
                    "WHERE id=%s",
                    (*updated.values(), aid),
                )
            conn.commit()
        finally:
            conn.close()

    fixed_title = fixed_body = fixed_src = fixed_time = failed = 0
    pending_render: list[dict] = []

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for aid, updated, err, needs_render in pool.map(work, rows):
            if err:
                failed += 1
                continue
            if needs_render:
                pending_render.append(
                    next(r for r in rows if int(r["id"]) == aid)
                )
            if updated:
                persist(aid, updated)

    # 第二阶段：无头浏览器渲染（串行，Playwright 的 greenlet 不能跨线程）
    rendered_ok = 0
    if pending_render:
        print(f"静态解析无正文 {len(pending_render)} 条，转无头浏览器渲染…")
        for i, r in enumerate(pending_render, 1):
            aid = int(r["id"])
            html = _render(r["url"])
            if not html:
                continue
            try:
                ad = get_adapter(r["adapter_name"])
                d = ad.parse_detail(html, url=r["url"])
            except Exception:  # noqa: BLE001
                continue
            updated: dict[str, object] = {}
            paras = clean_paragraphs(d.paragraphs)
            if paras:
                updated["body_text"] = "\n".join(paras)
                updated["content_hash"] = content_hash(paras)
            if not (r["title"] or "") and d.title:
                cand = clean_title(d.title)
                if cand and not _BAD_TITLE.search(cand) and len(cand) >= 6:
                    updated["title"] = cand
            if not (r["source_name"] or "") and d.source_name:
                cand = clean_source(d.source_name)
                if cand:
                    updated["source_name"] = cand
            if r["published_at_cst"] is None and d.published_text:
                try:
                    p = parse_published(d.published_text)
                    if p.value is not None:
                        updated["published_at_utc"] = to_utc_naive(p.value)
                        updated["published_at_cst"] = p.value
                        updated["time_precision"] = p.precision
                except Exception:  # noqa: BLE001
                    pass
            if updated:
                rendered_ok += 1
                persist(aid, updated)
            if i % 20 == 0:
                print(f"  渲染进度 {i}/{len(pending_render)}，已修 {rendered_ok}")

    print(f"完成：标题 +{fixed_title}，正文 +{fixed_body}，来源 +{fixed_src}，"
          f"时间 +{fixed_time}，其中渲染修复 {rendered_ok}，失败/无解 {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
