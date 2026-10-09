"""export 模块单元测试：export_csv 全量/筛选/格式。"""

from __future__ import annotations

import csv
import os
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest

from newsagg.export import COLUMNS, export_csv
from newsagg.query import ArticleFilter


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


class FakeSettings:
    def __init__(self, root: str) -> None:
        self.root = root


def _sample_rows():
    return [
        {
            "id": 1, "province_code": "32", "province_name": "江苏",
            "adapter_name": "jiangsu", "media_name": "中国江苏网",
            "title": "测试标题", "url": "http://example.com/1",
            "published_at_cst": datetime(2026, 10, 8, 12, 0, 0),
            "time_precision": "minute", "source_name": "来源",
            "quality_flags": "[]", "body_text": "正文内容",
        },
        {
            "id": 2, "province_code": "32", "province_name": "江苏",
            "adapter_name": "jiangsu", "media_name": "中国江苏网",
            "title": "=公式", "url": "http://example.com/2",
            "published_at_cst": None,
            "time_precision": "unknown", "source_name": "",
            "quality_flags": '["non_text_content"]', "body_text": "",
        },
    ]


class TestExportCsv:
    def test_no_filter_exports_all(self):
        conn = FakeConn()
        conn.queue(_sample_rows())
        with tempfile.TemporaryDirectory() as td:
            with patch("newsagg.export.get_settings", return_value=FakeSettings(td)), \
                 patch("newsagg.export.Database", return_value=FakeDB(conn)):
                out = os.path.join(td, "all.csv")
                result = export_csv(out)
                assert result == out
                assert os.path.exists(out)
            with open(out, encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.reader(fh))
            assert len(rows) == 3
            assert rows[0] == COLUMNS

    def test_with_province_filter(self):
        conn = FakeConn()
        conn.queue([_sample_rows()[0]])
        with tempfile.TemporaryDirectory() as td:
            with patch("newsagg.export.get_settings", return_value=FakeSettings(td)), \
                 patch("newsagg.export.Database", return_value=FakeDB(conn)):
                out = os.path.join(td, "filtered.csv")
                export_csv(out, ArticleFilter(province="江苏"))
                assert any("province_code" in s for s in conn.executed)

    def test_with_date_range(self):
        conn = FakeConn()
        conn.queue([_sample_rows()[0]])
        with tempfile.TemporaryDirectory() as td:
            with patch("newsagg.export.get_settings", return_value=FakeSettings(td)), \
                 patch("newsagg.export.Database", return_value=FakeDB(conn)):
                out = os.path.join(td, "date.csv")
                export_csv(out, ArticleFilter(date_from="2026-10-01", date_to="2026-10-08"))
                assert any("published_at_cst >=" in s for s in conn.executed)
                assert any("published_at_cst <=" in s for s in conn.executed)

    def test_csv_has_bom(self):
        conn = FakeConn()
        conn.queue(_sample_rows())
        with tempfile.TemporaryDirectory() as td:
            with patch("newsagg.export.get_settings", return_value=FakeSettings(td)), \
                 patch("newsagg.export.Database", return_value=FakeDB(conn)):
                out = os.path.join(td, "bom.csv")
                export_csv(out)
                with open(out, "rb") as fh:
                    head = fh.read(3)
                assert head == b"\xef\xbb\xbf"

    def test_csv_column_order(self):
        conn = FakeConn()
        conn.queue(_sample_rows())
        with tempfile.TemporaryDirectory() as td:
            with patch("newsagg.export.get_settings", return_value=FakeSettings(td)), \
                 patch("newsagg.export.Database", return_value=FakeDB(conn)):
                out = os.path.join(td, "cols.csv")
                export_csv(out)
                with open(out, encoding="utf-8-sig", newline="") as fh:
                    reader = csv.reader(fh)
                    header = next(reader)
                assert header == COLUMNS
                assert header[0] == "id"
                assert header[-1] == "body_text"

    def test_csv_row_count(self):
        conn = FakeConn()
        conn.queue(_sample_rows())
        with tempfile.TemporaryDirectory() as td:
            with patch("newsagg.export.get_settings", return_value=FakeSettings(td)), \
                 patch("newsagg.export.Database", return_value=FakeDB(conn)):
                out = os.path.join(td, "rows.csv")
                export_csv(out)
                with open(out, encoding="utf-8-sig", newline="") as fh:
                    rows = list(csv.reader(fh))
                assert len(rows) == 3

    def test_csv_cell_escapes_formula(self):
        conn = FakeConn()
        conn.queue(_sample_rows())
        with tempfile.TemporaryDirectory() as td:
            with patch("newsagg.export.get_settings", return_value=FakeSettings(td)), \
                 patch("newsagg.export.Database", return_value=FakeDB(conn)):
                out = os.path.join(td, "formula.csv")
                export_csv(out)
                with open(out, encoding="utf-8-sig", newline="") as fh:
                    rows = list(csv.reader(fh))
                assert rows[2][5] == "'=公式"

    def test_csv_none_published_outputs_empty(self):
        conn = FakeConn()
        conn.queue(_sample_rows())
        with tempfile.TemporaryDirectory() as td:
            with patch("newsagg.export.get_settings", return_value=FakeSettings(td)), \
                 patch("newsagg.export.Database", return_value=FakeDB(conn)):
                out = os.path.join(td, "none_date.csv")
                export_csv(out)
                with open(out, encoding="utf-8-sig", newline="") as fh:
                    rows = list(csv.reader(fh))
                assert rows[2][7] == ""

    def test_output_path_relative(self):
        conn = FakeConn()
        conn.queue(_sample_rows())
        with tempfile.TemporaryDirectory() as td:
            with patch("newsagg.export.get_settings", return_value=FakeSettings(td)), \
                 patch("newsagg.export.Database", return_value=FakeDB(conn)):
                result = export_csv("relative.csv")
                assert os.path.isabs(result)
                assert os.path.exists(result)
