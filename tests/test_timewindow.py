"""timewindow 模块单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta

from newsagg.timewindow import (
    INCREMENTAL_LOOKBACK_HOURS,
    JOB_FULL_RESCAN,
    JOB_INCREMENTAL,
    build_window,
    classify_moment,
    hourly_trigger_key,
    window_to_utc,
)


class TestBuildWindow:
    def test_first_ever_is_full_rescan_7days(self):
        # 北京时间 2026-10-08 12:00 = UTC 04:00
        now_utc = datetime(2026, 10, 8, 4, 0, 0)
        w = build_window(now_utc, last_discovery_success_at_utc=None, first_today=True)
        assert w.job_type == JOB_FULL_RESCAN
        # 7 天起点：当天 00:00 往前 6 天 = 10-02 00:00（北京时间）
        assert w.start_cst == datetime(2026, 10, 2, 0, 0, 0)
        assert w.end_cst == datetime(2026, 10, 8, 12, 0, 0)

    def test_first_today_full_rescan(self):
        now_utc = datetime(2026, 10, 8, 4, 0, 0)
        w = build_window(
            now_utc,
            last_discovery_success_at_utc=datetime(2026, 10, 8, 0, 0, 0),
            first_today=True,
        )
        assert w.job_type == JOB_FULL_RESCAN

    def test_incremental_uses_48h_lookback(self):
        now_utc = datetime(2026, 10, 8, 4, 0, 0)  # CST 12:00
        last = datetime(2026, 10, 8, 0, 0, 0)  # CST 08:00 → last_cst
        w = build_window(now_utc, last_discovery_success_at_utc=last, first_today=False)
        assert w.job_type == JOB_INCREMENTAL
        # last_cst=10-08 08:00, minus 48h = 10-06 08:00; 7天起点=10-02;取较晚者
        assert w.start_cst == datetime(2026, 10, 6, 8, 0, 0)

    def test_incremental_clamped_to_window_start(self):
        now_utc = datetime(2026, 10, 8, 4, 0, 0)  # CST 10-08 12:00
        # 上次发现在很早（7天窗口起点之前），增量起点应被夹到窗口起点
        last = datetime(2026, 9, 1, 0, 0, 0)
        w = build_window(now_utc, last_discovery_success_at_utc=last, first_today=False)
        assert w.job_type == JOB_INCREMENTAL
        assert w.start_cst == datetime(2026, 10, 2, 0, 0, 0)  # 7 天起点


class TestTriggerKey:
    def test_hour_key_is_cst(self):
        # UTC 2026-10-08 16:30 → CST 2026-10-09 00:30 → key 2026100900
        assert hourly_trigger_key(datetime(2026, 10, 8, 16, 30, 0)) == "2026100900"

    def test_same_hour_same_key(self):
        a = hourly_trigger_key(datetime(2026, 10, 8, 4, 5, 0))
        b = hourly_trigger_key(datetime(2026, 10, 8, 4, 55, 0))
        assert a == b == "2026100812"

    def test_classify_moment_alias(self):
        t = datetime(2026, 10, 8, 4, 0, 0)
        assert classify_moment(t) == hourly_trigger_key(t)


class TestWindowToUtc:
    def test_conversion(self):
        now_utc = datetime(2026, 10, 8, 4, 0, 0)
        w = build_window(now_utc, last_discovery_success_at_utc=None, first_today=True)
        start_utc, end_utc = window_to_utc(w)
        # CST 10-02 00:00 → UTC 10-01 16:00
        assert start_utc == datetime(2026, 10, 1, 16, 0, 0)
        # CST 10-08 12:00 → UTC 10-08 04:00
        assert end_utc == datetime(2026, 10, 8, 4, 0, 0)


def test_incremental_lookback_constant():
    assert INCREMENTAL_LOOKBACK_HOURS == 48
