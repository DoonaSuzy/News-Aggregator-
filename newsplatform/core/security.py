"""JWT 签发与校验（HS256）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

from newsplatform.core.config import get_settings
from newsplatform.core.exceptions import Unauthorized


def create_access_token(subject: str, *, extra: Optional[Dict[str, Any]] = None,
                        expires_minutes: Optional[int] = None) -> str:
    """签发访问令牌。``sub`` 为身份标识（用户名）。"""
    s = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or s.access_token_expire_minutes)
    payload: Dict[str, Any] = {"sub": subject, "iat": now, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    """校验并解码令牌；过期/非法抛 ``Unauthorized``。"""
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("invalid token") from exc


__all__ = ["create_access_token", "decode_access_token"]
