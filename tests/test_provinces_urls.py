"""provinces 与 urls 模块单元测试。"""

from __future__ import annotations

import hashlib

from newsagg.provinces import PROVINCES
from newsagg.urls import normalize_url, url_hash


class TestProvinces:
    def test_count_is_31(self):
        assert len(PROVINCES) == 31

    def test_codes_unique(self):
        codes = [c for c, _ in PROVINCES]
        assert len(codes) == len(set(codes)) == 31

    def test_names_unique(self):
        names = [n for _, n in PROVINCES]
        assert len(names) == len(set(names)) == 31

    def test_codes_are_2_digit(self):
        for code, _ in PROVINCES:
            assert len(code) == 2
            assert code.isdigit()

    def test_key_provinces_present(self):
        d = dict(PROVINCES)
        for code, name in [("11", "北京"), ("31", "上海"), ("50", "重庆"), ("65", "新疆"), ("15", "内蒙古")]:
            assert d.get(code) == name


class TestUrlHash:
    def test_length(self):
        assert len(url_hash("http://a.com/x")) == 64

    def test_stable(self):
        assert url_hash("http://a.com/x") == url_hash("http://a.com/x")

    def test_normalizes_before_hash(self):
        # 片段与跟踪参数不同，规范化后应一致
        assert url_hash("http://a.com/x#frag") == url_hash("http://a.com/x")
        assert url_hash("http://a.com/x?utm_source=1") == url_hash("http://a.com/x")


class TestNormalizeUrl:
    def test_strips_fragment(self):
        assert normalize_url("http://a.com/x#sec") == "http://a.com/x"

    def test_lowercases_host(self):
        assert normalize_url("http://A.COM/X") == "http://a.com/X"

    def test_drops_tracking_params(self):
        assert normalize_url("http://a.com/x?utm_source=1&utm_medium=2") == "http://a.com/x"
        assert normalize_url("http://a.com/x?spm=1&from=2&scene=3") == "http://a.com/x"

    def test_keeps_unknown_query(self):
        assert normalize_url("http://a.com/x?id=1") == "http://a.com/x?id=1"

    def test_keeps_scheme(self):
        assert normalize_url("https://a.com/x").startswith("https://")

    def test_idempotent(self):
        u = normalize_url("http://a.com/x?id=1")
        assert normalize_url(u) == u

    def test_empty(self):
        assert normalize_url("") == ""

