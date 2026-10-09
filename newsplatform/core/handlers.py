"""全局异常处理与请求中间件。

统一将各类异常转换为 :class:`ApiResponse`；并注入 ``X-Request-ID``
响应头、把 request_id 写入日志上下文。
"""

from __future__ import annotations

import logging
import uuid
from typing import List

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from newsplatform.core.exceptions import PlatformError
from newsplatform.core.logging import request_id_var
from newsplatform.core.responses import fail

logger = logging.getLogger("platform")


def _json(response, status: int, request: Request) -> JSONResponse:
    rid = request_id_var.get()
    body = response.model_copy(update={"request_id": rid}) if rid != "-" else response
    return JSONResponse(
        status_code=status,
        content=jsonable_encoder(body.model_dump()),
        headers={"X-Request-ID": rid},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_var.reset(token)

    @app.exception_handler(PlatformError)
    async def _platform_error(request: Request, exc: PlatformError):
        logger.warning("biz error %s: %s %s", exc.code, exc.message,
                       getattr(exc, "detail", ""))
        return _json(fail(exc.code, exc.message), exc.code, request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        errors: List[dict] = [
            {"field": ".".join(str(p) for p in e["loc"][1:]),
             "msg": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return _json(fail(422, "validation error", data={"errors": errors}), 422, request)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        return _json(fail(exc.status_code, str(exc.detail)), exc.status_code, request)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error: %s", exc)
        return _json(fail(500, "internal server error"), 500, request)


__all__ = ["register_exception_handlers"]
