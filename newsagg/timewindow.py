"""北京时间窗口与触发判定。

- 近 7 天 = 北京时间的「任务建立当天 + 前面 6 个自然日」，不是滚动 168 小时。
- 每天第一次触发做 7 天列表回扫（full_rescan）；同日后续触发做增量
  （incremental），从上次成功发现时间往前看 48 小时，且不早于当前 7 天起点。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from newsagg.cleaning import to_cst_naive, to_utc_naive

JOB_INCREMENTAL = "incremental"
JOB_FULL_RESCAN = "full_rescan"

#: 增量回看小时数
INCREMENTAL_LOOKBACK_HOURS = 48


@dataclass(frozen=True)
class Window:
    """一次任务的时间窗口（均为北京时间 naive）。"""

    start_cst: datetime
    end_cst: datetime
    job_type: str


def build_window(
    now_utc_naive: datetime,
    *,
    last_discovery_success_at_utc: datetime | None,
    first_today: bool,
) -> Window:
    """构造时间窗口。

    :param now_utc_naive: 当前 UTC naive 时间（建任务时刻）。
    :param last_discovery_success_at_utc: 上次列表发现成功时间（UTC naive），
        无则视为首次。
    :param first_today: 当天是否第一次触发。
    """
    now_cst = to_cst_naive(now_utc_naive)
    # 7 天起点：当天 00:00 往前数 6 个自然日
    window_start_cst = (now_cst - timedelta(days=6)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    window_end_cst = now_cst

    is_first_ever = last_discovery_success_at_utc is None
    if is_first_ever or first_today:
        return Window(window_start_cst, window_end_cst, JOB_FULL_RESCAN)

    # 增量：从上次成功发现时间往前看 48 小时，且不早于 7 天起点
    last_cst = to_cst_naive(last_discovery_success_at_utc)
    incremental_start = last_cst - timedelta(hours=INCREMENTAL_LOOKBACK_HOURS)
    start = max(incremental_start, window_start_cst)
    return Window(start, window_end_cst, JOB_INCREMENTAL)


def hourly_trigger_key(now_utc_naive: datetime) -> str:
    """按小时生成触发键（北京时间整点），用于同一小时不重复建批。"""
    now_cst = to_cst_naive(now_utc_naive)
    hour_start = now_cst.replace(minute=0, second=0, microsecond=0)
    return hour_start.strftime("%Y%m%d%H")


def classify_moment(now_utc_naive: datetime) -> str:
    """返回当前所属小时键（与 :func:`hourly_trigger_key` 相同，语义化别名）。"""
    return hourly_trigger_key(now_utc_naive)


def window_to_utc(window: Window) -> tuple[datetime, datetime]:
    """把窗口边界转换为 UTC naive（用于 SQL 比较）。"""
    return to_utc_naive(window.start_cst), to_utc_naive(window.end_cst)


__all__ = [
    "JOB_INCREMENTAL",
    "JOB_FULL_RESCAN",
    "INCREMENTAL_LOOKBACK_HOURS",
    "Window",
    "build_window",
    "hourly_trigger_key",
    "classify_moment",
    "window_to_utc",
]
