"""结构化日志（JSON）与 request_id 传播。

request_id 通过 contextvars 贯穿单次请求，供中间件与日志记录共用。
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

from pythonjsonlogger import json as jsonlogger

#: 当前请求的 request_id，默认 "-"
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: str = "INFO") -> logging.Logger:
    """配置并返回 ``platform`` logger（控制台 JSON）。"""
    logger = logging.getLogger("platform")
    logger.setLevel(level.upper())
    logger.propagate = False
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    fmt = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
        rename_fields={"levelname": "level", "asctime": "time", "name": "logger"},
    )
    handler.setFormatter(fmt)
    handler.addFilter(_RequestIdFilter())
    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("platform")


__all__ = ["setup_logging", "get_logger", "request_id_var"]
