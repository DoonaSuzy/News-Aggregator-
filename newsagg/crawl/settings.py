"""Scrapy 设置：并发、AutoThrottle、重定向、重试、自定义中间件、下载槽。

``scrapy_settings()`` 由 ``crawl/engine.py`` 的 ``runner()`` 使用，
构造一次抓取批次（``crawl-once``）的 :class:`CrawlerRunner` 设置。

设计约定（见文档 §2.3）：
- Asyncio 反应器（已在 ``newsagg/__init__.py`` 安装）。
- 并发 8，``DOWNLOAD_TIMEOUT`` 30。
- AutoThrottle：目标并发 8，最大延迟 60。
- 关 Cookie（站点无登录态）。
- 重试 2 次，仅针对 5xx/408。
- 关闭 Scrapy 重定向中间件（重定向由蜘蛛自行判定归属）。
- 注册 ``AccessPolicyMiddleware``(560) 与 ``PaceMiddleware``(590)。
- ``DOWNLOAD_SLOTS`` 给 guizhou 单独限流。
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
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "CONCURRENT_REQUESTS": s.concurrency,
        "CONCURRENT_REQUESTS_PER_DOMAIN": s.concurrency,
        "DOWNLOAD_TIMEOUT": s.download_timeout,
        "COOKIES_ENABLED": False,
        "USER_AGENT": s.user_agent,
        "ROBOTSTXT_OBEY": False,  # 由 AccessPolicyMiddleware 自行决策（贵州忽略）
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 2,
        "RETRY_HTTP_CODES": RETRY_HTTP_CODES,
        "REDIRECT_ENABLED": False,  # 关闭内置重定向中间件
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
