"""下载器中间件：访问策略与限速。

``AccessPolicyMiddleware``(560)
    放行 robots.txt 本身；页面返回 403/405/412/429 则记录阻断并 ``closeSpider``。

``PaceMiddleware``(590)
    把指定来源固定到独立下载槽，每次响应后把间隔设回，
    防止 AutoThrottle 把限速站点（guizhou）的间隔改短。
"""

from __future__ import annotations

from newsagg.crawl.settings import BLOCK_HTTP_CODES
from newsagg.logutil import get_logger

log = get_logger()

#: 需要独立下载槽 + 固定间隔的来源（adapter_name → 秒）
PACED_SOURCES = {"guizhou": 5}


class AccessPolicyMiddleware:
    """按状态码判定访问阻断，阻断即停止蜘蛛。"""

    def __init__(self) -> None:
        self._blocked = False

    def process_response(self, request, response, spider):  # noqa: ANN001
        # robots.txt 本身永远放行（贵州等忽略 robots 的来源不请求它）
        if request.url.rstrip("/").endswith("/robots.txt"):
            return response
        if response.status in BLOCK_HTTP_CODES:
            self._blocked = True
            reason = f"http_{response.status}"
            spider.session.note_block(request.url, response.status)
            spider.crawler.engine.close_spider(spider, reason)
        return response


class PaceMiddleware:
    """把限速来源固定到独立下载槽，响应后重置间隔。"""

    def process_request(self, request, spider):  # noqa: ANN001
        adapter_name = getattr(spider, "adapter_name", None)
        if adapter_name in PACED_SOURCES:
            request.meta["download_slot"] = adapter_name
        return None

    def process_response(self, request, response, spider):  # noqa: ANN001
        adapter_name = getattr(spider, "adapter_name", None)
        interval = PACED_SOURCES.get(adapter_name)
        if interval:
            # 直接把该槽的延迟设回固定值，抵消 AutoThrottle 的缩短
            slot = spider.crawler.engine.downloader.slots.get(adapter_name)
            if slot is not None:
                slot.delay = interval
        return response


__all__ = ["AccessPolicyMiddleware", "PaceMiddleware", "PACED_SOURCES"]
