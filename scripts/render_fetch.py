"""浏览器渲染抓取：对付正文由 JS 注入的省级站点。

纯 HTTP 抓到的页面只有模板占位符（江苏中国江苏网、广西广电、浙江在线部分频道、
四川新闻网、青海新闻网等），正文要靠浏览器渲染后才出现。本模块用 playwright
的 headless chromium 渲染后抽取标题、正文段落、来源、发布时间。

用法（命令行单页调试）::
    python scripts/render_fetch.py <adapter> <url> [<url> ...]

供回填脚本调用::
    from scripts.render_fetch import render_detail
    d = render_detail(url, wait_ms=2500)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BROWSER = None
PAGE = None

_FOOTER_HINT = re.compile(
    r"(版权所有|Copyright|ICP|备案号|主办单位|承办单位|技术支持|友情链接|"
    r"扫一扫|分享到|上一条|下一条|阅读次数|"
    r"modal window|Beginning of dialog|End of dialog|skip to main content)",
    re.I,
)


def _ensure_browser():
    """惰性启动一个 headless chromium（复用同一实例，避免反复冷启动）。"""
    global BROWSER, PAGE
    if BROWSER is None:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        BROWSER = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage"],
        )
        # 保存 playwright 上下文，进程退出时不必显式 stop
        globals()["_PW"] = pw
    return BROWSER


def render_html(url: str, *, wait_ms: int = 2500, timeout: int = 30000) -> str:
    """渲染 URL 并返回最终 HTML。"""
    browser = _ensure_browser()
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="zh-CN",
        viewport={"width": 1280, "height": 900},
    )
    try:
        page = ctx.new_page()
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=wait_ms)
        except Exception:  # noqa: BLE001
            page.wait_for_timeout(wait_ms)
        return page.content()
    finally:
        ctx.close()


def render_html_guarded(url: str, *, wait_ms: int = 2500, timeout: int = 30000,
                        wall_clock: int = 60) -> str | None:
    """带硬超时的渲染：在独立子进程里跑 Playwright，超时即 kill。

    Playwright 同步 API 的 greenlet 在 Windows 上偶发死锁（goto 有 timeout 但
    greenlet 整体卡住，进程 CPU=0 但浏览器子进程存活）。本函数把单页渲染放到
    独立子进程，父进程用 ``wall_clock`` 秒硬超时；超时则强制结束该子进程，
    不影响整个批次。子进程成功返回 HTML，失败/超时返回 ``None``。

    :param wall_clock: 子进程整体墙钟超时（秒），需大于 ``timeout``(毫秒)。
    """
    import base64
    import subprocess
    import sys
    import tempfile

    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    timeout_s = max(timeout / 1000.0 + 5.0, 1.0)
    hard = max(wall_clock, int(timeout_s) + 10)

    # 关键：子进程 stdout 走临时文件而非管道。Windows 上若用管道，
    # 超时 kill 直接子进程后，其派生的 chromium 孙进程仍继承管道句柄且不退出，
    # 父进程最终 communicate() 读管道会永久阻塞——即使 timeout 已触发。
    out_fd, out_path = tempfile.mkstemp(prefix="ro_", suffix=".b64")
    err_path = out_path + ".err"
    import os as _os

    _os.close(out_fd)
    proc = None
    try:
        with open(out_path, "wb") as out_fh, open(err_path, "wb") as err_fh:
            proc = subprocess.Popen(
                [sys.executable, "-m", "scripts.render_one", url,
                 str(wait_ms), str(timeout)],
                cwd=str(root),
                stdout=out_fh,
                stderr=err_fh,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            try:
                proc.wait(timeout=hard)
            except subprocess.TimeoutExpired:
                _kill_tree(proc)
                proc.wait(timeout=10)
                return None
            if proc.returncode != 0:
                return None
        out = Path(out_path).read_text(encoding="ascii", errors="ignore").strip()
    except Exception:  # noqa: BLE001
        if proc is not None and proc.poll() is None:
            _kill_tree(proc)
        return None
    finally:
        for p in (out_path, err_path):
            try:
                Path(p).unlink()
            except OSError:
                pass
    if not out:
        return None
    try:
        return base64.b64decode(out).decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def _kill_tree(proc) -> None:
    """结束子进程及其整棵进程树（Windows 用 taskkill /T /F）。"""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            timeout=15,
        )
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def render_detail(url: str, *, wait_ms: int = 2500) -> dict:
    """渲染并抽取 {title, paragraphs, source_name, published_text}。

    单页渲染走 :func:`render_html_guarded`（子进程 + 墙钟硬超时），
    避免 Playwright greenlet 在 Windows 上整体卡死拖垮整批。
    """
    html = render_html_guarded(url, wait_ms=wait_ms)
    if not html:
        return {"title": "", "paragraphs": [], "source_name": "", "published_text": ""}
    from parsel import Selector

    sel = Selector(text=html)
    title = ""
    og = sel.css("meta[property='og:title']::attr(content)").get()
    if og and len(og.strip()) >= 4:
        title = og.strip()
    if not title:
        h1 = sel.css("h1")
        if h1:
            title = "".join(h1[0].css("::text").getall()).strip()
    if not title:
        t = sel.css("title::text").get() or ""
        title = re.split(r"\s+[-_|—]\s+", t)[0].strip()

    paras: list[str] = []
    for p in sel.css("p"):
        text = " ".join(p.css("::text").getall()).strip()
        if len(text) < 15:
            continue
        link_text = "".join(p.css("a::text").getall()).strip()
        if link_text and len(link_text) > len(text) * 0.6:
            continue
        if _FOOTER_HINT.search(text) and len(text) < 80:
            continue
        paras.append(text)

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    src_m = re.search(r"来源\s*[：:]\s*([^\s]{2,25})", text)
    time_m = re.search(
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?[ T]?\d{0,2}:?\d{0,2}:?\d{0,2}", text
    )
    return {
        "title": title,
        "paragraphs": paras,
        "source_name": src_m.group(1).strip() if src_m else "",
        "published_text": time_m.group(0) if time_m else "",
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("用法: python scripts/render_fetch.py <adapter> <url> [...]")
        return 1
    for url in argv[2:]:
        try:
            d = render_detail(url)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {url} -> {type(exc).__name__}: {str(exc)[:80]}")
            continue
        print(f"--- {url}")
        print(f"    title  : {d['title'][:70]!r}")
        print(f"    source : {d['source_name'][:30]!r}")
        print(f"    time   : {d['published_text'][:30]!r}")
        print(f"    paras  : {len(d['paragraphs'])}  首段 "
              f"{(d['paragraphs'][0][:60] if d['paragraphs'] else '')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
