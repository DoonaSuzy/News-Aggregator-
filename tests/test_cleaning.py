"""cleaning 模块单元测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from newsagg.cleaning import (
    PRECISION_DATE,
    PRECISION_MINUTE,
    PRECISION_SECOND,
    PRECISION_UNKNOWN,
    clean_paragraphs,
    clean_source,
    clean_title,
    content_hash,
    csv_cell,
    parse_published,
    quality_flags,
    to_cst_naive,
    to_utc_naive,
    FLAG_NON_TEXT,
)


class TestCleanTitle:
    def test_strips_tags_and_collapses_ws(self):
        assert clean_title("  <b>标题</b>\n  内容  ") == "标题 内容"

    def test_removes_zero_width(self):
        assert clean_title("标\u200b题") == "标题"

    def test_none_and_empty(self):
        assert clean_title(None) == ""
        assert clean_title("") == ""
        assert clean_title("   ") == ""


class TestCleanSource:
    def test_strips_source_prefix(self):
        assert clean_source("来源：人民日报") == "人民日报"
        assert clean_source("来源:新华网") == "新华网"

    def test_no_prefix_unchanged(self):
        assert clean_source("央视新闻") == "央视新闻"

    def test_none(self):
        assert clean_source(None) == ""


class TestCleanParagraphs:
    def test_drops_empty_and_tags(self):
        out = clean_paragraphs(["<p>第一段</p>", "   ", "第二段", None, ""])
        assert out == ["第一段", "第二段"]

    def test_collapses_ws(self):
        assert clean_paragraphs(["  多   个    空格  "]) == ["多 个 空格"]


class TestContentHash:
    def test_stable(self):
        h1 = content_hash(["a", "b"])
        h2 = content_hash(["a", "b"])
        assert h1 == h2
        assert len(h1) == 64

    def test_differs(self):
        assert content_hash(["a"]) != content_hash(["b"])


class TestQualityFlags:
    def test_media_only_flagged(self):
        assert FLAG_NON_TEXT in quality_flags([], is_media_only=True)

    def test_empty_text_flagged(self):
        assert FLAG_NON_TEXT in quality_flags([])

    def test_normal_no_flag(self):
        assert quality_flags(["正文内容"]) == []


class TestParsePublished:
    @pytest.mark.parametrize(
        "raw,precision",
        [
            ("2026-10-03 15:04:05", PRECISION_SECOND),
            ("2026/10/3 15:04:05", PRECISION_SECOND),
            ("2026-10-03 15:04", PRECISION_MINUTE),
            ("2026年10月3日 15:04", PRECISION_MINUTE),
            ("2026-10-03", PRECISION_DATE),
            ("2026年10月3日", PRECISION_DATE),
            ("10-03 15:04", PRECISION_MINUTE),
        ],
    )
    def test_formats(self, raw, precision):
        result = parse_published(raw)
        assert result.precision == precision
        assert result.value is not None

    def test_second_precision_value(self):
        r = parse_published("2026-10-03 15:04:05")
        assert r.value == datetime(2026, 10, 3, 15, 4, 5)

    def test_no_year_uses_default(self):
        r = parse_published("10-03 15:04", default_year=2020)
        assert r.value == datetime(2020, 10, 3, 15, 4)

    def test_unparseable(self):
        r = parse_published("没有时间")
        assert r.value is None
        assert r.precision == PRECISION_UNKNOWN

    def test_empty(self):
        assert parse_published(None).value is None
        assert parse_published("").precision == PRECISION_UNKNOWN


class TestCsvCell:
    def test_formula_prefix_escaped(self):
        assert csv_cell("=1+1") == "'=1+1"
        assert csv_cell("+x") == "'+x"
        assert csv_cell("-x") == "'-x"
        assert csv_cell("@x") == "'@x"

    def test_normal_unchanged(self):
        assert csv_cell("普通文本") == "普通文本"

    def test_none(self):
        assert csv_cell(None) == ""

    def test_number(self):
        assert csv_cell(42) == "42"


class TestTimeConversion:
    def test_roundtrip(self):
        cst = datetime(2026, 10, 3, 12, 0, 0)
        utc = to_utc_naive(cst)
        assert utc == datetime(2026, 10, 3, 4, 0, 0)
        assert to_cst_naive(utc) == cst

    def test_offset_is_8h(self):
        assert to_utc_naive(datetime(2026, 1, 1, 0, 0)) == datetime(2025, 12, 31, 16, 0)
