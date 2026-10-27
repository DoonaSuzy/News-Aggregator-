"""发布时间护栏的回归测试。

这些值都来自真实库里的脏数据：3 条 2610 年、2 条 1956 年。
它们会把 `channel=all` 的首页前三名长期占住（按发布时间倒序）。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from newsagg.timeguard import MIN_PLAUSIBLE_YEAR, clamp_published

WINDOW_END = datetime(2026, 10, 9, 23, 59, 59)


class TestClampPublished:
    def test_normal_date_kept(self):
        value = datetime(2026, 10, 8, 20, 59)
        assert clamp_published(value, WINDOW_END) == value

    def test_ancient_year_dropped(self):
        """1956 年那条：正文写「1956年10月8日 国防部第五研究院成立」。"""
        assert clamp_published(datetime(1956, 10, 8), WINDOW_END) is None

    def test_future_year_dropped(self):
        """2610 年那三条：解析器把多段数字拼进了同一个日期。"""
        assert clamp_published(datetime(2610, 8, 6), WINDOW_END) is None

    def test_one_day_tolerance_for_future(self):
        """抓取当天跨时区的稿子允许超前 1 天。"""
        assert clamp_published(datetime(2026, 10, 10, 12), WINDOW_END) is not None
        assert clamp_published(datetime(2026, 10, 11, 12), WINDOW_END) is None

    def test_none_window_falls_back_to_now(self):
        """没传窗口时也不能放过未来日期——2610 必须被拦住。"""
        now = datetime(2026, 10, 9, 12)
        assert clamp_published(datetime(2610, 8, 6), None, now=now) is None
        assert clamp_published(datetime(2026, 10, 8), None, now=now) is not None

    def test_none_value_passthrough(self):
        assert clamp_published(None, WINDOW_END) is None

    def test_boundary_year(self):
        """正好等于阈值年份保留，早一年丢弃。"""
        assert clamp_published(datetime(MIN_PLAUSIBLE_YEAR, 1, 1), WINDOW_END) is not None
        assert clamp_published(datetime(MIN_PLAUSIBLE_YEAR - 1, 12, 31), WINDOW_END) is None

    @pytest.mark.parametrize(
        "raw",
        [datetime(1934, 5, 1), datetime(1999, 12, 31), datetime(2610, 8, 6)],
    )
    def test_known_garbage_all_dropped(self, raw):
        assert clamp_published(raw, WINDOW_END) is None
