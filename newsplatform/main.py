"""FastAPI 应用入口。

装配：统一响应/异常、限流、自动文档、生命周期（启动时建表、开发环境播种管理员）。
运行：``uvicorn newsplatform.main:app --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from newsplatform.api.router import api_router
from newsplatform.core.config import get_settings
from newsplatform.core.handlers import register_exception_handlers
from newsplatform.core.logging import setup_logging
from newsplatform.core.ratelimit import limiter
from newsplatform.core.responses import ok

logger = setup_logging()
settings = get_settings()

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：确保表存在（幂等）。生产建议改用 Alembic 迁移。
    try:
        from newsplatform.models.orm import Base
        from newsplatform.core.database import get_engine
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database schema ensured")
    except Exception:  # noqa: BLE001
        logger.exception("schema ensure failed (will retry on request)")
    # 开发环境：播种一个管理员账号便于联调
    if settings.env == "development":
        try:
            await _seed_admin()
        except Exception:  # noqa: BLE001
            logger.exception("seed admin failed")
    yield


async def _seed_admin() -> None:
    from newsplatform.core.database import get_session_factory
    from newsplatform.models.orm import User
    from newsplatform.repositories.article_repo import SourceRepository
    from sqlalchemy import select
    from werkzeug.security import generate_password_hash

    factory = get_session_factory()
    async with factory() as session:
        existing = await SourceRepository(session).get_by_username("admin")
        if existing is None:
            session.add(User(
                username="admin",
                password_hash=generate_password_hash("admin123"),
                role="admin", is_active=True,
            ))
            await session.commit()
            logger.info("seeded admin user (username=admin)")


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description=(
        "省级新闻聚合数据中台对外接口。\n\n"
        "- 统一响应信封：`{code, message, data, request_id, timestamp}`\n"
        "- 鉴权：`POST /api/v1/auth/login` 获取 Bearer 令牌\n"
        "- 文档：`/docs`（Swagger UI）、`/redoc`、`/openapi.json`"
    ),
    openapi_tags=[
        {"name": "健康检查", "description": "存活/就绪探针"},
        {"name": "鉴权", "description": "登录与令牌"},
        {"name": "文章", "description": "文章检索与详情"},
        {"name": "来源与统计", "description": "来源、省份覆盖、总览统计"},
    ],
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# 限流
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# 统一异常与 request_id
register_exception_handlers(app)

# 业务路由
app.include_router(api_router, prefix=API_PREFIX)


@app.get("/", tags=["健康检查"], summary="服务信息")
async def root():
    return ok({"name": settings.app_name, "version": "0.2.0", "env": settings.env},
              message="welcome")


__all__ = ["app"]
