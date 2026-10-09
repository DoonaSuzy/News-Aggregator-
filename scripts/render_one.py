"""单页渲染子进程入口：渲染一个 URL，把 HTML 写到 stdout（base64）。

由 ``scripts/render_fetch.py`` 的 ``render_html_guarded`` 以子进程方式调用，
配合 wall-clock 超时使用——Playwright 同步 API 的 greenlet 在 Windows 上偶发
死锁时，父进程可整体 kill 本子进程而不拖垮整个批次。

字符集处理：部分省级站（青海/云南等）服务 GBK 但不声明 charset，Playwright
按默认编码误读成乱码，``page.content()`` 再把乱码串当 UTF-8 输出。本入口用
``route`` 拦截文档响应，按「meta charset → header charset → utf-8 试探 →
gb18030」嗅探真实字符集后，以显式 ``charset=`` fulfill，使浏览器正确解码；
JS 注入的正文仍会正常渲染。

用法（勿直接手调，仅供子进程调用）::

    python -m scripts.render_one <url> [wait_ms] [timeout_ms]
"""

from __future__ import annotations

import base64
import re
import sys

_META_CHARSET = re.compile(rb"""charset\s*=\s*["']?\s*([a-zA-Z0-9\-_]+)""", re.I)


def _sniff_charset(raw: bytes, header: str) -> str:
    """从 header/meta/试探推断字符集。"""
    m = re.search(r"charset=([a-zA-Z0-9\-_]+)", header or "", re.I)
    if m:
        enc = m.group(1)
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            pass
    m = _META_CHARSET.search(raw[:4096])
    if m:
        enc = m.group(1).decode("ascii", "ignore")
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            pass
    # 无声明：UTF-8 能干净解码就用 utf-8，否则中文站多半是 GBK 系
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "gb18030"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m scripts.render_one <url> [wait_ms] [timeout_ms]",
              file=sys.stderr)
        return 2
    url = argv[1]
    wait_ms = int(argv[2]) if len(argv) > 2 else 2500
    timeout = int(argv[3]) if len(argv) > 3 else 30000

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
        )

        def _handle(route):
            try:
                resp = route.fetch()
                body = resp.body()
                ct = resp.headers.get("content-type", "text/html")
                enc = _sniff_charset(body, ct)
                # 以显式字符集 fulfill，浏览器据此正确解码原始字节
                route.fulfill(response=resp, body=body,
                              content_type=f"text/html; charset={enc}")
            except Exception:  # noqa: BLE001
                route.continue_()

        page = ctx.new_page()
        page.route("**/*", _handle)
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=wait_ms)
            except Exception:  # noqa: BLE001
                page.wait_for_timeout(wait_ms)
            html = page.content()
        finally:
            browser.close()

    sys.stdout.write(base64.b64encode(html.encode("utf-8")).decode("ascii"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

