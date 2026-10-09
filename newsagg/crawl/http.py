"""HTTP 客户端：UA 伪装、超时、并发/间隔控制。"""

from __future__ import annotations

import threading
import time

import requests


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout: int = 30,
        concurrency: int = 8,
        interval: float = 0.0,
    ) -> None:
        self._timeout = timeout
        self._interval = interval
        self._last_request = 0.0
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def get(self, url: str) -> str | None:
        """GET 页面，返回文本；失败返回 None。"""
        self._throttle()
        try:
            resp = self._session.get(url, timeout=self._timeout, allow_redirects=True)
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        # 探测编码
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def close(self) -> None:
        self._session.close()

    def _throttle(self) -> None:
        if self._interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._last_request + self._interval - now
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()


__all__ = ["HttpClient"]
