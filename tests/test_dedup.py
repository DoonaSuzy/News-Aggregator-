"""dedup 模块单元测试：URL 布隆过滤器 + 多源同文检测。

- ``UrlBloom`` 基于 Redis 位图，用 fakeredis 离线验证 maybe_seen / add / seen_or_add。
- ``find_duplicate_article`` 需要 DB 连接，这里用一个最小假游标验证 SQL 语义边界。
"""

from __future__ import annotations

import fakeredis

from newsagg.crawl.dedup import (
    BLOOM_KEY,
    UrlBloom,
    _bit_positions,
    find_duplicate_article,
)
from newsagg.cleaning import FLAG_DUPLICATE


def make_bloom() -> UrlBloom:
    return UrlBloom(fakeredis.FakeStrictRedis(decode_responses=True))


class TestBitPositions:
    def test_deterministic(self):
        assert _bit_positions("a" * 64) == _bit_positions("a" * 64)

    def test_within_range(self):
        for pos in _bit_positions("deadbeef" * 8):
            assert 0 <= pos < (1 << 24)

    def test_distinct_inputs_differ(self):
        assert _bit_positions("a" * 64) != _bit_positions("b" * 64)

    def test_four_positions(self):
        assert len(_bit_positions("c" * 64)) == 4


class TestUrlBloom:
    def test_unseen_returns_false(self):
        b = make_bloom()
        assert b.maybe_seen("a" * 64) is False

    def test_seen_after_add(self):
        b = make_bloom()
        b.add("a" * 64)
        assert b.maybe_seen("a" * 64) is True

    def test_seen_or_add_first_false_then_true(self):
        b = make_bloom()
        assert b.seen_or_add("b" * 64) is False  # 未见 → 标记
        assert b.seen_or_add("b" * 64) is True   # 已见 → 跳过

    def test_independent_hashes(self):
        b = make_bloom()
        b.add("a" * 64)
        # 不同 url_hash 互不影响（假设无位冲突）
        assert b.maybe_seen("f" * 64) is False

    def test_uses_named_key(self):
        b = make_bloom()
        b.add("d" * 64)
        # 位图写入落在 BLOOM_KEY 下
        assert b._client.exists(BLOOM_KEY) == 1


class TestFindDuplicate:
    def test_flag_constant(self):
        assert FLAG_DUPLICATE == "duplicate"

    def test_empty_hash_returns_none(self):
        # 空 content_hash 不应触发查询
        assert find_duplicate_article(None, source_id=1, content_hash="") is None

    def test_hit_returns_row(self):
        class FakeCur:
            def __init__(self, row):
                self._row = row

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a):
                pass

            def fetchone(self):
                return self._row

        class FakeConn:
            def __init__(self, row):
                self._row = row

            def cursor(self):
                return FakeCur(self._row)

        row = {"id": 10, "adapter_name": "fujian", "province_code": "35"}
        dup = find_duplicate_article(FakeConn(row), source_id=2, content_hash="x")
        assert dup["adapter_name"] == "fujian"

    def test_miss_returns_none(self):
        class FakeCur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a):
                pass

            def fetchone(self):
                return None

        class FakeConn:
            def cursor(self):
                return FakeCur()

        assert find_duplicate_article(FakeConn(), source_id=2, content_hash="y") is None
