"""离线测试夹具：共享内存 SQLite + TestClient + 种子数据。

关键点：
- 用 ``file:...?mode=memory&cache=shared`` 共享内存库 + StaticPool，
  让所有连接看到同一份数据，规避 Windows 文件句柄占用问题。
- 建表+种子必须在 TestClient 的 anyio portal 事件循环内执行，
  否则 aiosqlite 连接跨事件循环复用会崩溃。
"""

from __future__ import annotations

import os

import pytest

# 必须在导入 newsplatform 之前设置，走 sqlite 覆盖
os.environ["PLATFORM_DATABASE_URL_OVERRIDE"] = (
    "sqlite+aiosqlite:///file:newsagg_test?mode=memory&cache=shared&uri=true"
)
os.environ["PLATFORM_JWT_SECRET"] = "test-secret-key-at-least-32-bytes-long-xxxx"
os.environ["PLATFORM_ENV"] = "test"

from newsplatform.core.config import reset_settings  # noqa: E402
from newsplatform.core.database import (  # noqa: E402
    get_engine, get_session_factory, reset_engine,
)
from newsplatform.main import app  # noqa: E402
from newsplatform.models.orm import Article, Base, Province, Source, User  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh():
    reset_settings()
    reset_engine()
    yield
    reset_settings()
    reset_engine()


async def _reset_and_seed() -> None:
    """重建表 + 种子（共享内存库，portal 循环内执行）。"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = get_session_factory()
    async with factory() as session:
        session.add_all([
            Province(code="32", name="江苏"),
            Province(code="35", name="福建"),
            Source(id=1, adapter_name="jiangsu", media_name="新华日报",
                   province_code="32", column_url="http://x", status="enabled",
                   article_count=2),
            Source(id=2, adapter_name="fujian", media_name="东南网",
                   province_code="35", column_url="http://y", status="enabled",
                   article_count=1),
            Article(source_id=1, url_hash="h1", url="http://x/1", title="江苏新闻一",
                    body_text="正文一", source_name="新华日报",
                    published_at_cst=None, content_hash="c1", quality_flags="[]"),
            Article(source_id=2, url_hash="h2", url="http://y/2", title="福建新闻二",
                    body_text="正文二", source_name="东南网",
                    published_at_cst=None, content_hash="c2", quality_flags="[]"),
            User(username="admin",
                 password_hash=generate_password_hash("admin123"),
                 role="admin", is_active=True),
        ])
        await session.commit()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.portal.call(_reset_and_seed)
        yield c


__all__ = ["client"]
