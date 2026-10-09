"""依赖注入：数据库会话、当前登录身份。

- ``DbSession``：请求级异步会话
- ``CurrentSubject``：从 Bearer 令牌解析出的身份（强制鉴权）
- ``OptionalSubject``：令牌可选（用于「登录后可查看更多」的场景）
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated, Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from newsplatform.core.database import get_db
from newsplatform.core.security import decode_access_token

DbSession = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_subject(
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)],
) -> str:
    if creds is None or not creds.credentials:
        from newsplatform.core.exceptions import Unauthorized
        raise Unauthorized("missing bearer token")
    payload = decode_access_token(creds.credentials)
    subject = payload.get("sub")
    if not subject:
        from newsplatform.core.exceptions import Unauthorized
        raise Unauthorized("token missing subject")
    return str(subject)


async def get_optional_subject(
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)],
) -> Optional[str]:
    if creds is None or not creds.credentials:
        return None
    try:
        payload = decode_access_token(creds.credentials)
    except Exception:  # noqa: BLE001 - 可选鉴权，失败即匿名
        return None
    return str(payload.get("sub")) if payload.get("sub") else None


CurrentSubject = Annotated[str, Depends(get_current_subject)]
OptionalSubject = Annotated[Optional[str], Depends(get_optional_subject)]


__all__ = [
    "DbSession", "CurrentSubject", "OptionalSubject",
    "get_current_subject", "get_optional_subject",
]
