"""classify 投递分类单元测试（run / wait / ack 三类决策）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from newsagg.classify import Decision, JobSnapshot, classify_delivery
from newsagg.errors import JobTerminal, LeaseBusy, NotDue

NOW = datetime(2026, 10, 8, 12, 0, 0)


class TestTerminalAck:
    def test_succeeded_acked(self):
        s = JobSnapshot(status="succeeded")
        assert classify_delivery(s, now_utc=NOW, owner="w1") == Decision.ACK

    def test_partial_acked(self):
        s = JobSnapshot(status="partial")
        assert classify_delivery(s, now_utc=NOW, owner="w1") == Decision.ACK

    def test_failed_no_retry_acked(self):
        s = JobSnapshot(status="failed", retry_at_utc=None)
        assert classify_delivery(s, now_utc=NOW, owner="w1") == Decision.ACK

    def test_failed_retry_due_acked(self):
        s = JobSnapshot(status="failed", retry_at_utc=NOW - timedelta(minutes=1))
        assert classify_delivery(s, now_utc=NOW, owner="w1") == Decision.ACK


class TestRun:
    def test_queued_runs(self):
        s = JobSnapshot(status="queued")
        assert classify_delivery(s, now_utc=NOW, owner="w1") == Decision.RUN

    def test_running_no_lease_runs(self):
        s = JobSnapshot(status="running")
        assert classify_delivery(s, now_utc=NOW, owner="w1") == Decision.RUN

    def test_own_valid_lease_runs(self):
        s = JobSnapshot(
            status="running",
            lease_token="tok",
            lease_owner="w1",
            lease_until_utc=NOW + timedelta(minutes=5),
        )
        assert classify_delivery(s, now_utc=NOW, owner="w1") == Decision.RUN

    def test_expired_lease_runs(self):
        s = JobSnapshot(
            status="running",
            lease_token="tok",
            lease_owner="w2",
            lease_until_utc=NOW - timedelta(minutes=1),
        )
        assert classify_delivery(s, now_utc=NOW, owner="w1") == Decision.RUN


class TestWait:
    def test_others_valid_lease_waits(self):
        s = JobSnapshot(
            status="running",
            lease_token="tok",
            lease_owner="w2",
            lease_until_utc=NOW + timedelta(minutes=5),
        )
        with pytest.raises(LeaseBusy):
            classify_delivery(s, now_utc=NOW, owner="w1")


class TestRetryWait:
    def test_retry_wait_not_due(self):
        s = JobSnapshot(status="retry_wait", retry_at_utc=NOW + timedelta(minutes=5))
        with pytest.raises(NotDue):
            classify_delivery(s, now_utc=NOW, owner="w1")

    def test_retry_wait_due_acked(self):
        # 重试时间已到，由调度器重新建任务，此处 ack 旧消息
        s = JobSnapshot(status="retry_wait", retry_at_utc=NOW - timedelta(minutes=1))
        assert classify_delivery(s, now_utc=NOW, owner="w1") == Decision.ACK
