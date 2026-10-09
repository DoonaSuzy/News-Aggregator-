"""newsagg 顶层包。

在任何模块导入 ``twisted.internet.reactor`` 之前安装 AsyncioSelectorReactor
（Scrapy 2.19 的异步蜘蛛入口 ``async start()`` 需要 asyncio 反应器）。
"""

from __future__ import annotations

__version__ = "0.1.0"

# --- 反应器安装（必须在任何 twisted reactor 导入之前） -------------------
import asyncio  # noqa: E402

try:  # pragma: no cover - 取决于安装环境
    from scrapy.utils.reactor import install_reactor

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
except Exception:  # pragma: no cover
    # 已经安装过反应器（重复导入）时忽略
    pass

# 确保事件循环策略在 Windows 上可用
if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):  # pragma: no cover
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

__all__ = ["__version__"]
