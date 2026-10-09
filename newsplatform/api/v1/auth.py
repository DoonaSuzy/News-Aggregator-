"""鉴权：登录签发 JWT。

登录成功后返回 Bearer 令牌，用于访问需要鉴权的接口。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from newsplatform.core.deps import DbSession
from newsplatform.core.ratelimit import limiter
from newsplatform.core.responses import ApiResponse, ok
from newsplatform.schemas.auth import LoginRequest, TokenResponse
from newsplatform.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/login",
    response_model=ApiResponse[TokenResponse],
    summary="登录获取令牌",
    description="使用用户名/密码登录，成功返回 JWT Bearer 令牌。受独立限流保护。",
    responses={401: {"description": "用户名或密码错误"}},
)
@limiter.limit("10/minute")
async def login(payload: LoginRequest, request: Request, db: DbSession) -> ApiResponse:
    token = await AuthService(db).login(payload.username, payload.password)
    return ok(token.model_dump(), message="login success")


__all__ = ["router"]
