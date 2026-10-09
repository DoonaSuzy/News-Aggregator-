"""robots.txt 决策（按站点解析）。

贵州站点（guizhou）按规范明确忽略 robots.txt。
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from newsagg.crawl.http import HttpClient

# 忽略 robots 的站点白名单
IGNORE_ROBOTS = {"guizhou"}

_cache: dict[str, RobotFileParser | None] = {}


def _robots_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "http", parts.netloc, "/robots.txt", "", ""))


def is_allowed(url: str, *, adapter_name: str, user_agent: str, http: HttpClient) -> bool:
    """判断是否允许抓取该 URL。"""
    if adapter_name in IGNORE_ROBOTS:
        return True
    host = urlsplit(url).netloc
    parser = _cache.get(host)
    if host not in _cache:
        robots_url = _robots_url(url)
        content = http.get(robots_url)
        if content is None:
            parser = None  # 取不到 robots 时默认放行
        else:
            parser = RobotFileParser()
            parser.parse(content.splitlines())
        _cache[host] = parser
    if parser is None:
        return True
    return parser.can_fetch(user_agent, url)


def reset_cache() -> None:
    _cache.clear()


__all__ = ["is_allowed", "reset_cache", "IGNORE_ROBOTS"]
