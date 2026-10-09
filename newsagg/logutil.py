"""日志工具：控制台 + 按天轮转文件。"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler


def configure_stdio() -> None:
    """强制标准输出/错误为 UTF-8（Windows 控制台友好）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def setup_logging(log_dir: str | None = None, *, level: int = logging.INFO) -> logging.Logger:
    """配置并返回 ``newsagg`` logger。

    输出到控制台与 ``logs/newsagg.log``（按天轮转，保留 14 份）。
    """
    configure_stdio()
    logger = logging.getLogger("newsagg")
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    directory = log_dir or "logs"
    try:
        os.makedirs(directory, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            os.path.join(directory, "newsagg.log"),
            when="midnight",
            backupCount=14,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        # 无法写文件时仅保留控制台
        pass

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("newsagg")


__all__ = ["setup_logging", "get_logger", "configure_stdio"]
