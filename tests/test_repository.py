"""repo 层单元测试：用假连接验证 SQL 契约与决策逻辑，无需真实 MySQL。

假连接只实现 repo 用到的最小游标协议（``with conn.cursor() as cur``、
``execute/fetchone/fetchall/rowcount/lastrowid``），并记录执行过的 SQL，
从而在不连库的情况下验证来源 / 任务 / 租约 / 文章 的读写语义。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from newsagg import errors
from newsagg.repo import Repository


class FakeCursor:
    """最小 pymysql 游标替代：按脚本返回结果并记录 SQL。"""

    def __init__(self, conn: "FakeConn") -> None:
        self._conn = conn
        self._rows: list[dict] = []
        self._idx = 0
        self.rowcount = 0
        self.lastrowid = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def execute(self, sql: str, params=None) -> None:
        self._conn.executed.append(" ".join(sql.split()))
        if self._conn.script:
            self._rows = self._conn.script.pop(0) or []
        else:
            self._rows = []
        self._idx = 0
        self.rowcount = len(self._rows)
        self.lastrowid = self._conn.next_id

    def fetchone(self):
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self):
        rows = self._rows[self._idx:]
        self._idx = len(self._rows)
        return rows


class FakeConn:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.script: list[list[dict]] = []
        self.next_id = 0
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        pass

    def queue(self, rows: list[dict]) -> None:
        """enqueue 一条 execute 的返回结果集（一次一个 execute）。"""
        self.script.append(list(rows))


NOW = datetime(2026, 10, 8, 12, 0, 0)
FUTURE = datetime(2026, 10, 8, 12, 5, 0)
PAST = datetime(2026, 10, 8, 11, 0, 0)


class FakeDB:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    def connect(self) -> FakeConn:
        return self._conn


def repo_with(conn: FakeConn) -> Repository:
    return Repository(db=FakeDB(conn))

LEASE_FUTURE = datetime(2099, 1, 1)  # 恒晚于真实 utcnow，用于「租约有效」场景


def src_row(**over):
    row = {
        "id": 1, "adapter_name": "fujian", "province_code": "35",
        "media_name": "东南网", "column_url": "http://www.fjsen.com",
        "verification_status": "enabled", "lease_token": None,
        "lease_owner": None, "lease_until_utc": None,
    }
    row.update(over)
    return row


def job_row(**over):
    row = {
        "id": 10, "source_id": 1, "job_type": "incremental", "status": "queued",
        "window_start_cst": NOW, "window_end_cst": NOW, "retry_at_utc": None,
        "lease_token": None, "lease_owner": None, "lease_until_utc": None,
    }
    row.update(over)
    return row


class TestGetSource:
    def test_by_id(self):
        conn = FakeConn(); conn.queue([src_row()])
        s = repo_with(conn).get_source(conn, source_id=1)
        assert s is not None and s.adapter_name == "fujian" and s.id == 1

    def test_by_adapter_name(self):
        conn = FakeConn(); conn.queue([src_row()])
        s = repo_with(conn).get_source(conn, adapter_name="fujian")
        assert s.province_code == "35" and s.media_name == "东南网"

    def test_missing_returns_none(self):
        conn = FakeConn(); conn.queue([])
        assert repo_with(conn).get_source(conn, source_id=99) is None

    def test_requires_key(self):
        import pytest
        with pytest.raises(ValueError):
            repo_with(FakeConn()).get_source(FakeConn())


class TestEnableSource:
    def test_enable_when_articles_exist(self):
        conn = FakeConn(); conn.queue([{"n": 3}])
        assert repo_with(conn).enable_source(conn, "fujian") is True
        assert any("verification_status = 'enabled'" in q for q in conn.executed)

    def test_enable_blocked_without_articles(self):
        conn = FakeConn(); conn.queue([{"n": 0}])
        assert repo_with(conn).enable_source(conn, "fujian") is False
        # 不应产生 UPDATE
        assert not any("UPDATE sources" in q for q in conn.executed)

    def test_resume_clears_cooldown(self):
        conn = FakeConn()
        repo_with(conn).resume_source(conn, "fujian")
        assert any("cooldown_until_utc = NULL" in q for q in conn.executed)

    def test_pause_sets_reason(self):
        conn = FakeConn()
        repo_with(conn).pause_source(conn, "fujian", "blocked_403")
        assert any("verification_status = 'paused'" in q for q in conn.executed)


class TestCreateJob:
    def test_created_returns_id(self):
        conn = FakeConn(); conn.next_id = 42; conn.queue([{}])
        jid = repo_with(conn).create_job(
            conn, source_id=1, trigger_key="2026100912", job_type="incremental",
            window_start_cst=NOW, window_end_cst=NOW)
        assert jid == 42

    def test_duplicate_returns_none(self):
        conn = FakeConn(); conn.queue([])  # rowcount=0 → 已存在
        jid = repo_with(conn).create_job(
            conn, source_id=1, trigger_key="k", job_type="incremental",
            window_start_cst=NOW, window_end_cst=NOW)
        assert jid is None



class TestAcquireLease:
    """acquire_lease 用真实 utcnow 判定租约有效期，故用 2099 作为「有效」。"""

    def test_queued_claim_succeeds(self):
        conn = FakeConn()
        conn.queue([{  # find_open_job SELECT ... FOR UPDATE
            "status": "queued", "job_type": "incremental",
            "window_start_cst": NOW, "window_end_cst": NOW,
            "lease_owner": None, "lease_until_utc": None,
        }])
        result = repo_with(conn).acquire_lease(conn, 10, "worker-1", lease_seconds=300)
        assert result is not None
        job_row_obj, lease = result
        assert job_row_obj.status == "running"
        assert lease.owner == "worker-1"
        assert any("attempt_count = attempt_count + 1" in q for q in conn.executed)

    def test_terminal_job_raises(self):
        conn = FakeConn()
        conn.queue([{
            "status": "succeeded", "job_type": "incremental",
            "window_start_cst": NOW, "window_end_cst": NOW,
            "lease_owner": "w", "lease_until_utc": None,
        }])
        with pytest.raises(errors.JobTerminal):
            repo_with(conn).acquire_lease(conn, 10, "w2", lease_seconds=300)

    def test_others_active_lease_raises_busy(self):
        conn = FakeConn()
        conn.queue([{
            "status": "running", "job_type": "incremental",
            "window_start_cst": NOW, "window_end_cst": NOW,
            "lease_owner": "other", "lease_until_utc": LEASE_FUTURE,
        }])
        with pytest.raises(errors.LeaseBusy):
            repo_with(conn).acquire_lease(conn, 10, "w2", lease_seconds=300)

    def test_missing_job_raises_keyerror(self):
        conn = FakeConn(); conn.queue([])
        with pytest.raises(KeyError):
            repo_with(conn).acquire_lease(conn, 999, "w", lease_seconds=300)


class TestRenewLease:
    def test_renew_hit_returns_true(self):
        conn = FakeConn(); conn.queue([{}, {}])  # rowcount=1 → 命中
        assert repo_with(conn).renew_lease(
            conn, source_id=1, token="tok", lease_seconds=300) is True

    def test_renew_miss_returns_false(self):
        conn = FakeConn(); conn.queue([])  # rowcount=0 → 令牌不匹配
        assert repo_with(conn).renew_lease(
            conn, source_id=1, token="stale", lease_seconds=300) is False


class TestSaveArticle:
    def test_new_article_saved(self):
        conn = FakeConn(); conn.next_id = 7
        conn.queue([])   # SELECT existing → 无
        conn.queue([{}])  # INSERT
        res = repo_with(conn).save_article(
            conn, source_id=1, url_hash="h", url="http://x", title="t",
            body_text="body", content_hash="c")
        assert res.outcome == "saved" and res.article_id == 7

    def test_same_hash_skipped(self):
        conn = FakeConn()
        conn.queue([{"id": 5, "content_hash": "c"}])
        res = repo_with(conn).save_article(
            conn, source_id=1, url_hash="h", url="http://x", title="t",
            body_text="body", content_hash="c")
        assert res.outcome == "skipped" and res.article_id == 5
        assert not any("UPDATE articles" in q for q in conn.executed)

    def test_changed_hash_updates(self):
        conn = FakeConn()
        conn.queue([{"id": 5, "content_hash": "old"}])
        res = repo_with(conn).save_article(
            conn, source_id=1, url_hash="h", url="http://x", title="t",
            body_text="newbody", content_hash="c")
        assert res.outcome == "updated" and res.article_id == 5
        assert any("UPDATE articles" in q for q in conn.executed)


class TestFinishJobAndRetry:
    def test_finish_job_writes_counts(self):
        conn = FakeConn()
        repo_with(conn).finish_job(
            conn, job_id=10, status="succeeded", discovered=20, saved=15,
            checkpoint_cst=NOW, stop_reason=None, advance_discovery=True)
        joined = " ".join(conn.executed)
        assert "status=%s, discovered_count=%s, saved_count=%s" in joined
        assert "last_discovery_success_at_utc=CURRENT_TIMESTAMP" in joined
        assert "UPDATE job_attempts" in joined

    def test_finish_job_no_discovery_advance(self):
        conn = FakeConn()
        repo_with(conn).finish_job(conn, job_id=10, status="partial", saved=3)
        assert not any("last_discovery_success_at_utc" in q for q in conn.executed)

    def test_set_retry(self):
        conn = FakeConn()
        repo_with(conn).set_retry(conn, job_id=10, retry_minutes=30, stop_reason="blocked")
        assert any("status='retry_wait'" in q for q in conn.executed)


class TestUpsertDiscovered:
    def test_new_returns_true(self):
        conn = FakeConn(); conn.queue([{}])  # rowcount=1 → 新插入
        assert repo_with(conn).upsert_discovered(
            conn, source_id=1, job_id=10, url_hash="h", url="http://x") is True

    def test_duplicate_returns_false(self):
        conn = FakeConn(); conn.queue([])  # rowcount=0 → 已存在
        assert repo_with(conn).upsert_discovered(
            conn, source_id=1, job_id=10, url_hash="h", url="http://x") is False

