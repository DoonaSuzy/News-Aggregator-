"""汇总 v1 路由。"""

from __future__ import annotations

from fastapi import APIRouter

from newsplatform.api.v1 import articles, auth, health, sources

api_router = APIRouter()
api_router.include_router(health.router, tags=["健康检查"])
api_router.include_router(auth.router, prefix="/auth", tags=["鉴权"])
api_router.include_router(articles.router, prefix="/articles", tags=["文章"])
api_router.include_router(sources.router, tags=["来源与统计"])

__all__ = ["api_router"]
