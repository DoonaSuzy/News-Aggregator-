"""自定义异常类型。"""

from __future__ import annotations


class NewsAggError(Exception):
    """所有 newsagg 异常的基类。"""


class ConfigError(NewsAggError):
    """配置缺失或不合法。"""


class LeaseRejected(NewsAggError):
    """旧令牌尝试更新已被他人持有的资源。"""


class LeaseBusy(NewsAggError):
    """他人（重试进程）正持有有效租约，本进程需等待。"""


class JobTerminal(NewsAggError):
    """任务已处于终态，不再接受状态推进。"""


class NotDue(NewsAggError):
    """重试时间未到，暂时不能重新执行。"""


__all__ = [
    "NewsAggError",
    "ConfigError",
    "LeaseRejected",
    "LeaseBusy",
    "JobTerminal",
    "NotDue",
]
