"""环境变量与运行时配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*_a, **_k):  # type: ignore
        return False


def project_root() -> Path:
    """定位项目根目录，可用 ``NEWSAGG_ROOT`` 覆盖。"""
    override = os.environ.get("NEWSAGG_ROOT")
    if override:
        return Path(override).resolve()
    # 本文件位于 <root>/newsagg/config.py
    return Path(__file__).resolve().parent.parent


def _load_env() -> None:
    root = project_root()
    load_dotenv(root / ".env")


@dataclass
class Settings:
    """从环境变量派生的运行时配置。"""

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "newsagg"
    mysql_password: str = ""
    mysql_database: str = "newsagg"
    redis_url: str = "redis://127.0.0.1:6379/0"

    log_dir: str = ""
    worker_count: int = 2

    # 租约与预算默认值
    lease_seconds: int = 300          # 5 分钟租约
    lease_renew_seconds: int = 60     # 60 秒续租
    max_articles_per_job: int = 500
    max_requests_per_job: int = 2000
    download_timeout: int = 30
    concurrency: int = 8
    autothrottle_max_delay: int = 60

    user_agent: str = "newsagg/0.1 (educational local aggregator)"

    @property
    def root(self) -> Path:
        return project_root()

    @property
    def resolved_log_dir(self) -> Path:
        if self.log_dir:
            return Path(self.log_dir)
        return self.root / "logs"

    @classmethod
    def from_env(cls) -> "Settings":
        _load_env()

        def _int(name: str, default: int) -> int:
            raw = os.environ.get(name)
            try:
                return int(raw) if raw not in (None, "") else default
            except ValueError:
                return default

        return cls(
            mysql_host=os.environ.get("NEWSAGG_MYSQL_HOST", "127.0.0.1"),
            mysql_port=_int("NEWSAGG_MYSQL_PORT", 3306),
            mysql_user=os.environ.get("NEWSAGG_MYSQL_USER", "newsagg"),
            mysql_password=os.environ.get("NEWSAGG_MYSQL_PASSWORD", ""),
            mysql_database=os.environ.get("NEWSAGG_MYSQL_DATABASE", "newsagg"),
            redis_url=os.environ.get("NEWSAGG_REDIS_URL", "redis://127.0.0.1:6379/0"),
            log_dir=os.environ.get("NEWSAGG_LOG_DIR", ""),
            worker_count=_int("NEWSAGG_WORKER_COUNT", 2),
            lease_seconds=_int("NEWSAGG_LEASE_SECONDS", 300),
            lease_renew_seconds=_int("NEWSAGG_LEASE_RENEW_SECONDS", 60),
            max_articles_per_job=_int("NEWSAGG_MAX_ARTICLES_PER_JOB", 500),
            max_requests_per_job=_int("NEWSAGG_MAX_REQUESTS_PER_JOB", 2000),
            download_timeout=_int("NEWSAGG_DOWNLOAD_TIMEOUT", 30),
            concurrency=_int("NEWSAGG_CONCURRENCY", 8),
        )


# 全局单例（惰性）
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings() -> None:
    """测试用：清空缓存。"""
    global _settings
    _settings = None


__all__ = [
    "Settings",
    "project_root",
    "get_settings",
    "reset_settings",
]
