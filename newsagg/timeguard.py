"""发布时间可信度护栏。

为什么需要
----------
详情页的发布时间抽取有多级回退：先找专门的时间选择器，找不到就
**在整页文本里扫第一个像日期的字符串**。后者会把正文里的历史日期当成发布时间：

- 一篇 2026 年的航天报道，正文第一段写「1956年10月8日，国防部第五研究院成立」
  → 整篇被标成 1956-10-08；
- 另一批稿子存成了 2610-08-06（正文只有「10月8日电」，无年份）。

实测 `newsagg` 库里有 3 条未来日期、2 条 1956 年的记录，它们会把
`channel=all` 的首页前三名长期占住（按发布时间倒序）。

规则
----
越界即**按未知处理**（置 ``None`` + ``time_precision=unknown``），而不是猜一个值：

- 早于 ``min_year``（默认 2000）：页脚的版权年份区间、正文引用的历史年份都会被误抓；
- 晚于窗口结束时间 + 1 天：抓取当天的稿子可能带时区偏差，留 1 天容差。

为什么不在解析层直接丢弃：解析层不知道「窗口」，只有调度侧知道这次采集覆盖到哪天。
"""

from __future__ import annotations

from datetime import datetime, timedelta

__all__ = ["MIN_PLAUSIBLE_YEAR", "clamp_published"]

#: 早于此年份一律视为抽取错误。
#: 取 2000 是因为采集的是「当日新闻」：比 2000 年更早的日期只可能来自页脚或正文引用，
#: 不可能是这篇文章的发布时间。
MIN_PLAUSIBLE_YEAR = 2000


def clamp_published(
    value: datetime | None,
    window_end: datetime | None,
    *,
    min_year: int = MIN_PLAUSIBLE_YEAR,
    future_tolerance_days: int = 1,
    now: datetime | None = None,
) -> datetime | None:
    """把不可信的发布时间收敛为 ``None``。

    Args:
        value: 解析出的发布时间（北京时间，naive）。
        window_end: 本次采集窗口的结束时间。为 ``None`` 时退回用 ``now``——
            不能因为「没传窗口」就放弃未来检查，2610 年那种值必须拦住。
        min_year: 早于该年份视为抽取错误。
        future_tolerance_days: 允许超前的天数（时区/跨天容差）。
        now: 参考的「当前时间」，仅测试需要固定它。

    Returns:
        可信则原样返回，不可信返回 ``None``。
    """
    if value is None:
        return None
    if value.year < min_year:
        return None
    reference = window_end or now or datetime.now()
    if value > reference + timedelta(days=future_tolerance_days):
        return None
    return value
