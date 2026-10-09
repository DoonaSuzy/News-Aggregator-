"""Scrapy 设置：并发、AutoThrottle、重定向、重试、自定义中间件、下载槽。

``scrapy_settings()`` 由 ``crawl/engine.py`` 的 ``runner()`` 使用，
构造一次抓取批次（``crawl-once``）的 :class:`CrawlerRunner` 设置。

设计约定（见文档 §2.3）：
- 并发 8，``DOWNLOAD_TIMEOUT`` 30。
- AutoThrottle：目标并发 8，最大延迟 60。
- 开 Cookie（站点无登录态，但有站点用一次性 Cookie 做反爬校验）。
- 重试 2 次，仅针对 5xx/408。
- 开启 Scrapy 重定向（最多 5 跳）：省级栏目页普遍是 http→https 的 301/302，
  不跟随会让列表回调收到 3xx 被静默丢弃，任务空跑结束。
- 注册 ``AccessPolicyMiddleware``(560) 与 ``PaceMiddleware``(590)。
- ``DOWNLOAD_SLOTS`` 给 guizhou 单独限流。

反应器：不覆盖 ``TWISTED_REACTOR``。实测在 Windows + Python 3.13 +
Twisted 26.4.0 下，强制 ``AsyncioSelectorReactor`` 会让异步蜘蛛
``async start()`` 挂起；Twisted 默认的 Windows 反应器可正常驱动。
"""

from __future__ import annotations

from newsagg.config import get_settings

#: 需要重试的状态码
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408]

#: 视为「访问被阻断」的状态码（触发停机与冷却）
BLOCK_HTTP_CODES = {403, 405, 412, 429}


def scrapy_settings(*, overrides: dict | None = None) -> dict:
    """返回一份 Scrapy 设置字典。"""
    s = get_settings()
    settings = {
        "CONCURRENT_REQUESTS": s.concurrency,
        "CONCURRENT_REQUESTS_PER_DOMAIN": s.concurrency,
        "DOWNLOAD_TIMEOUT": s.download_timeout,
        # 开启 Cookie：南海网等站点用 C3VK 这类一次性 Cookie 做反爬校验，
        # 不带 Cookie 会陷入 302 自跳循环（站点无登录态，无隐私影响）。
        "COOKIES_ENABLED": True,
        "USER_AGENT": s.user_agent,
        "ROBOTSTXT_OBEY": False,  # 由 AccessPolicyMiddleware 自行决策（贵州忽略）
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 2,
        "RETRY_HTTP_CODES": RETRY_HTTP_CODES,
        # 大量省级栏目页是 http→https 的 301/302（红网、南方网、大众网…），
        # 关闭重定向会让 list 回调收到 3xx 被 HttpErrorMiddleware 静默丢弃，
        # 表现为「discovered=0 直接 finished」。这里开启内置重定向兜底。
        "REDIRECT_ENABLED": True,
        "REDIRECT_MAX_TIMES": 5,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": s.concurrency,
        "AUTOTHROTTLE_MAX_DELAY": s.autothrottle_max_delay,
        "AUTOTHROTTLE_START_DELAY": 1.0,
        "AUTOTHROTTLE_DEBUG": False,
        "LOG_LEVEL": "WARNING",  # Scrapy 自身日志降噪，业务日志走 newsagg logger
        "TELNETCONSOLE_ENABLED": False,
        "DOWNLOAD_HANDLERS_BASE": {
            "file": "scrapy.core.downloader.handlers.file.FileDownloadHandler",
            "http": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
            "https": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
            "data": "scrapy.core.downloader.handlers.datauri.DataURIDownloadHandler",
        },
        "DOWNLOADER_MIDDLEWARES": {
            # 关闭内置 RobotsTxt 中间件，改由 AccessPolicyMiddleware 决策
            "scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware": None,
            "newsagg.crawl.middlewares.AccessPolicyMiddleware": 560,
            "newsagg.crawl.middlewares.PaceMiddleware": 590,
        },
        # guizhou 单独限流槽：并发降到 1，每次间隔由 PaceMiddleware 设回 5 秒
        "DOWNLOAD_SLOTS": {
            "guizhou": {
                "concurrency": 1,
                "delay": 5,
            },
        },
    }
    if overrides:
        settings.update(overrides)
    return settings


__all__ = ["scrapy_settings", "RETRY_HTTP_CODES", "BLOCK_HTTP_CODES"]
