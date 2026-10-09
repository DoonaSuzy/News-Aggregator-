"""统一请求响应格式。

所有对外接口返回统一信封::

    {"code": 0, "message": "ok", "data": {...}, "request_id": "...", "timestamp": "..."}

``code`` 语义：0 成功；其余为业务错误码（对齐 HTTP 语义，见 exceptions）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None
    request_id: Optional[str] = None
    timestamp: str = Field(default_factory=_now_iso)


def ok(data: Any = None, *, message: str = "ok",
       request_id: Optional[str] = None) -> ApiResponse:
    return ApiResponse(code=0, message=message, data=data, request_id=request_id)


def fail(code: int, message: str, *,
         request_id: Optional[str] = None, data: Any = None) -> ApiResponse:
    return ApiResponse(code=code, message=message, data=data, request_id=request_id)


__all__ = ["ApiResponse", "ok", "fail"]
