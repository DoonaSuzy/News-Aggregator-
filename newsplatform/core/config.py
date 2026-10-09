"""平台配置。

独立于爬虫，使用 ``PLATFORM_`` 环境变量前缀，读取项目根 ``.env``。
数据库默认指向容器服务名 ``mysql``/``redis``，便于 compose 网络内互访。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PLATFORM_", env_file=".env", extra="ignore"
    )

    # 应用
    app_name: str = "News Aggregator Platform"
    env: str = "production"
    debug: bool = False

    # 数据库（默认容器服务名）
    db_host: str = "mysql"
    db_port: int = 3306
    db_user: str = "platform"
    db_password: str = "platform_dev_pwd"
    db_name: str = "newsagg_platform"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False
    #: 直接覆盖连接串（测试用 sqlite）；留空则按上面的分项拼接 MySQL
    database_url_override: str = ""

    # Redis（缓存 + 限流后端）
    redis_url: str = "redis://redis:6379/0"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    # 限流默认值（slowapi 语法）
    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    """测试用：清空配置缓存。"""
    get_settings.cache_clear()


__all__ = ["Settings", "get_settings", "reset_settings"]
