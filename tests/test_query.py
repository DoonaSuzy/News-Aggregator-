"""query 模块单元测试：ArticleFilter / build_where / 格式化 / ArticleQuery。"""

from __future__ import annotations

from datetime import datetime

import pytest

from newsagg.query import (
    ArticleFilter,
    ArticleQuery,
    build_where,
    flags_text,
    format_cst,
    parse_day,
)


class FakeCursor:
    def __init__(self, conn: "FakeConn") -> None:
        self._conn = conn
        self._rows: list[dict] = []
        self._idx = 0

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

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass

    def queue(self, rows: list[dict]) -> None:
        self.script.append(list(rows))


class FakeDB:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    def connect(self) -> FakeConn:
        return self._conn


class TestArticleFilter:
    def test_defaults(self):
        flt = ArticleFilter()
        assert flt.province is None
        assert flt.day is None
        assert flt.date_from is None
        assert flt.date_to is None
        assert flt.keyword is None
        assert flt.body_only is False
        assert flt.unknown_time is False
        assert flt.limit == 50
        assert flt.offset == 0

    def test_custom_values(self):
        flt = ArticleFilter(
            province="江苏", day="2026-10-08", keyword="测试",
            body_only=True, unknown_time=True, limit=10, offset=5,
        )
        assert flt.province == "江苏"
        assert flt.day == "2026-10-08"
        assert flt.keyword == "测试"
        assert flt.body_only is True
        assert flt.unknown_time is True
        assert flt.limit == 10
        assert flt.offset == 5


class TestBuildWhere:
    def test_no_conditions(self):
        clause, params = build_where(ArticleFilter())
        assert clause == ""
        assert params == []

    def test_province_by_name(self):
        clause, params = build_where(ArticleFilter(province="江苏"))
        assert "s.province_code = %s" in clause
        assert params == ["32"]

    def test_province_by_code(self):
        clause, params = build_where(ArticleFilter(province="35"))
        assert "s.province_code = %s" in clause
        assert params == ["35"]

    def test_province_unknown(self):
        clause, params = build_where(ArticleFilter(province="不存在"))
        assert "province_code" not in clause
        assert params == []

    def test_day_single(self):
        clause, params = build_where(ArticleFilter(day="2026-10-08"))
        assert "BETWEEN" in clause
        assert params == [datetime(2026, 10, 8, 0, 0, 0), datetime(2026, 10, 8, 23, 59, 59)]

    def test_date_range(self):
        clause, params = build_where(ArticleFilter(date_from="2026-10-01", date_to="2026-10-08"))
        assert ">=" in clause
        assert "<=" in clause
        assert params == [datetime(2026, 10, 1, 0, 0, 0), datetime(2026, 10, 8, 23, 59, 59)]

    def test_keyword_both(self):
        clause, params = build_where(ArticleFilter(keyword="测试"))
        assert "title LIKE" in clause
        assert "body_text LIKE" in clause
        assert "OR" in clause
        assert params == ["%测试%", "%测试%"]

    def test_keyword_body_only(self):
        clause, params = build_where(ArticleFilter(keyword="测试", body_only=True))
        assert "body_text LIKE" in clause
        assert "title LIKE" not in clause
        assert params == ["%测试%"]

    def test_unknown_time(self):
        clause, params = build_where(ArticleFilter(unknown_time=True))
        assert "time_precision = 'unknown'" in clause
        assert params == []

    def test_combined(self):
        flt = ArticleFilter(province="福建", day="2026-10-08", keyword="经济")
        clause, params = build_where(flt)
        assert "province_code" in clause
        assert "BETWEEN" in clause
        assert "LIKE" in clause
        assert " AND " in clause
        assert len(params) == 5


class TestParseDay:
    def test_valid(self):
        start, end = parse_day("2026-10-08")
        assert start == datetime(2026, 10, 8, 0, 0, 0)
        assert end == datetime(2026, 10, 8, 23, 59, 59)

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_day("not-a-date")


class TestFormatCst:
    def test_none(self):
        assert format_cst(None) == ""

    def test_datetime(self):
        dt = datetime(2026, 10, 8, 15, 30, 45)
        assert format_cst(dt) == "2026-10-08 15:30:45"


class TestFlagsText:
    def test_none(self):
        assert flags_text(None) == "正常"

    def test_empty_list(self):
        assert flags_text([]) == "正常"

    def test_list(self):
        assert flags_text(["a", "b"]) == "a; b"

    def test_json_string(self):
        assert flags_text('["x"]') == "x"

    def test_invalid_json(self):
        assert flags_text("not json") == "not json"


class TestArticleQuery:
    def test_count(self):
        conn = FakeConn()
        conn.queue([{"n": 42}])
        q = ArticleQuery(db=FakeDB(conn))
        result = q.count(conn, ArticleFilter())
        assert result == 42
        assert any("COUNT(*)" in s for s in conn.executed)

    def test_matching_ids(self):
        conn = FakeConn()
        conn.queue([{"id": 1}, {"id": 2}, {"id": 3}])
        q = ArticleQuery(db=FakeDB(conn))
        ids = q.matching_ids(conn, ArticleFilter())
        assert ids == [1, 2, 3]

    def test_fetch_ids(self):
        conn = FakeConn()
        conn.queue([
            {"id": 1, "title": "t1"},
            {"id": 2, "title": "t2"},
        ])
        q = ArticleQuery(db=FakeDB(conn))
        rows = q.fetch_ids(conn, [1, 2])
        assert len(rows) == 2
        assert rows[0]["title"] == "t1"
        assert rows[1]["title"] == "t2"

    def test_fetch_ids_empty(self):
        conn = FakeConn()
        q = ArticleQuery(db=FakeDB(conn))
        assert q.fetch_ids(conn, []) == []

    def test_search_articles_pagination(self):
        conn = FakeConn()
        conn.queue([{"n": 5}])
        conn.queue([{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}])
        conn.queue([
            {"id": 2, "title": "t2"},
            {"id": 3, "title": "t3"},
        ])
        q = ArticleQuery(db=FakeDB(conn))
        rows, total = q.search_articles(conn, ArticleFilter(limit=2, offset=1))
        assert total == 5
        assert len(rows) == 2
        assert rows[0]["id"] == 2
        assert rows[1]["id"] == 3

    def test_search_articles_empty(self):
        conn = FakeConn()
        conn.queue([{"n": 0}])
        conn.queue([])
        q = ArticleQuery(db=FakeDB(conn))
        rows, total = q.search_articles(conn, ArticleFilter())
        assert total == 0
        assert rows == []

    def test_get_article(self):
        conn = FakeConn()
        conn.queue([{"id": 1, "title": "测试标题"}])
        q = ArticleQuery(db=FakeDB(conn))
        row = q.get_article(conn, 1)
        assert row is not None
        assert row["title"] == "测试标题"

    def test_get_article_not_found(self):
        conn = FakeConn()
        conn.queue([])
        q = ArticleQuery(db=FakeDB(conn))
        assert q.get_article(conn, 999) is None
