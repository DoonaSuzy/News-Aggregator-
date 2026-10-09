"""业务异常体系。

每个异常携带 HTTP 语义 ``code`` 与面向用户的 ``message``，由全局处理器
统一转换为 :class:`ApiResponse`。
"""

from __future__ import annotations

from typing import Optional


class PlatformError(Exception):
    """平台业务异常基类。"""

    code: int = 500
    message: str = "internal error"

    def __init__(self, message: Optional[str] = None, *, code: Optional[int] = None):
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        super().__init__(self.message)


class BadRequest(PlatformError):
    code = 400
    message = "bad request"


class Unauthorized(PlatformError):
    code = 401
    message = "unauthorized"


class Forbidden(PlatformError):
    code = 403
    message = "forbidden"


class NotFound(PlatformError):
    code = 404
    message = "not found"


class Conflict(PlatformError):
    code = 409
    message = "conflict"


class RateLimited(PlatformError):
    code = 429
    message = "too many requests"


class DependencyUnavailable(PlatformError):
    code = 503
    message = "dependency unavailable"


__all__ = [
    "PlatformError", "BadRequest", "Unauthorized", "Forbidden",
    "NotFound", "Conflict", "RateLimited", "DependencyUnavailable",
]
