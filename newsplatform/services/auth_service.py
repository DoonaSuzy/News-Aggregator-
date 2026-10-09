"""登录鉴权业务逻辑。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from werkzeug.security import check_password_hash

from newsplatform.core.exceptions import Unauthorized
from newsplatform.core.security import create_access_token
from newsplatform.models.orm import User
from newsplatform.repositories.article_repo import SourceRepository
from newsplatform.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SourceRepository(session)

    async def login(self, username: str, password: str) -> TokenResponse:
        user: User | None = await self.repo.get_by_username(username)
        if user is None or not user.is_active:
            raise Unauthorized("用户名或密码错误")
        if not check_password_hash(user.password_hash, password):
            raise Unauthorized("用户名或密码错误")
        token = create_access_token(
            user.username, extra={"role": user.role, "uid": user.id}
        )
        return TokenResponse(
            access_token=token, token_type="bearer",
            expires_in=_expire_seconds(),
        )


def _expire_seconds() -> int:
    from newsplatform.core.config import get_settings
    return get_settings().access_token_expire_minutes * 60


__all__ = ["AuthService"]
