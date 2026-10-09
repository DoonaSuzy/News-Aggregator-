"""接口限流（slowapi）。

默认按客户端 IP 维度限流；单容器内存计数足够。如需多实例共享计数，
可将 ``storage_uri`` 指向 Redis（见平台 README）。
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from newsplatform.core.config import get_settings

_s = get_settings()
limiter = Limiter(key_func=get_remote_address, default_limits=[_s.rate_limit_default])


__all__ = ["limiter"]
