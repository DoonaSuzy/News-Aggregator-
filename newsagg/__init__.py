"""newsagg 顶层包。

不强制安装反应器：Scrapy 2.19 的异步蜘蛛入口 ``async start()`` 使用
Twisted 默认反应器即可，无需（也不应）强制 asyncio 反应器——详见下方说明。
"""

from __future__ import annotations

__version__ = "0.1.0"

# --- 反应器说明 -----------------------------------------------------------
# 不在导入期强制安装 asyncio 反应器。实测在 Windows + Python 3.13 +
# Twisted 26.4.0 下，AsyncioSelectorReactor 会让 Scrapy 的异步蜘蛛
# ``async start()`` 挂起（事件循环不与 Twisted 正确对接，首请求永不发出）。
# Twisted 默认的 Windows selectreactor 能正常驱动异步蜘蛛，故交由 Scrapy
# 自行选择反应器（见 crawl/settings.py 不再覆盖 TWISTED_REACTOR）。

__all__ = ["__version__"]
