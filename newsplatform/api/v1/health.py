"""健康检查与就绪探针。

- ``/health``：存活探针（liveness），不依赖外部服务，恒返回 ok。
- ``/health/ready``：就绪探针（readiness），检查 MySQL/Redis 连通性。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from newsplatform.core.deps import DbSession
from newsplatform.core.responses import ApiResponse, ok
from newsplatform.schemas.common import Page  # noqa: F401  (保持包导入稳定)

router = APIRouter()


@router.get(
    "/health",
    response_model=ApiResponse,
    summary="存活探针",
    description="服务进程是否存活，不依赖外部组件。",
)
async def health() -> ApiResponse:
    return ok({"status": "alive"}, message="healthy")


@router.get(
    "/health/ready",
    response_model=ApiResponse,
    summary="就绪探针",
    description="检查数据库与缓存连通性；任一项不可用返回 503。",
    responses={503: {"description": "依赖不可用"}},
)
async def ready(db: DbSession) -> ApiResponse:
    checks: dict[str, str] = {}
    degraded = False

    # MySQL
    try:
        await db.execute(text("SELECT 1"))
        checks["mysql"] = "ok"
    except Exception:  # noqa: BLE001
        checks["mysql"] = "down"
        degraded = True

    # Redis（尽力而为，失败不影响 200 语义判定为 degraded）
    try:
        import redis.asyncio as aioredis
        from newsplatform.core.config import get_settings
        client = aioredis.from_url(get_settings().redis_url)
        try:
            await client.ping()
            checks["redis"] = "ok"
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001
        checks["redis"] = "down"
        degraded = True

    if degraded:
        from newsplatform.core.exceptions import DependencyUnavailable
        raise DependencyUnavailable("dependencies unavailable")
    return ok({"status": "ready", "checks": checks}, message="ready")


__all__ = ["router"]
