"""异步数据库引擎与会话（SQLAlchemy 2.x async）。

默认 ``mysql+aiomysql``；测试可通过 ``PLATFORM_DATABASE_URL_OVERRIDE``
指向 ``sqlite+aiosqlite`` 实现离线验证。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from newsplatform.core.config import get_settings

_engine = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine():
    global _engine
    if _engine is None:
        s = get_settings()
        connect_args = {}
        kwargs = {
            "echo": s.db_echo,
            "pool_pre_ping": True,
            "future": True,
        }
        if s.database_url.startswith("mysql"):
            kwargs.update(pool_size=s.db_pool_size, max_overflow=s.db_max_overflow,
                          pool_recycle=1800)
        if s.database_url.startswith("sqlite"):
            # 共享内存 + 单连接池：所有会话看到同一份数据，且规避 Windows
            # 文件句柄占用问题（离线测试用）
            connect_args = {"check_same_thread": False}
            kwargs.update(poolclass=StaticPool)
        _engine = create_async_engine(
            s.database_url, connect_args=connect_args, **kwargs
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), class_=AsyncSession, expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：请求级会话，结束即关闭。"""
    factory = get_session_factory()
    async with factory() as session:
        yield session


def reset_engine() -> None:
    """测试用：丢弃引擎与会话工厂（下次访问时重建）。"""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


__all__ = [
    "get_engine", "get_session_factory", "get_db", "reset_engine",
]
