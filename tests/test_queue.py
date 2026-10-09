"""queue 模块单元测试（基于 fakeredis 的 Redis Stream 语义验证）。"""

from __future__ import annotations

import fakeredis

from newsagg.queue import GROUP, STREAM, StreamQueue


def make_queue() -> StreamQueue:
    return StreamQueue(client=fakeredis.FakeStrictRedis(decode_responses=True))


class TestPublishConsume:
    def test_ensure_group_idempotent(self):
        q = make_queue()
        q.ensure_group()
        q.ensure_group()  # 二次调用不抛 BUSYGROUP

    def test_publish_returns_id(self):
        q = make_queue()
        q.ensure_group()
        mid = q.publish(1, {"a": 1})
        assert mid is not None

    def test_read_new_roundtrip(self):
        q = make_queue()
        q.ensure_group()
        q.publish(42, {"job_type": "full_rescan"})
        msgs = q.read_new(count=1, block_ms=0)
        assert len(msgs) == 1
        assert msgs[0].job_id == 42
        assert msgs[0].payload == {"job_type": "full_rescan"}

    def test_read_new_empty(self):
        q = make_queue()
        q.ensure_group()
        assert q.read_new(count=1, block_ms=0) == []

    def test_read_new_consumes_once(self):
        q = make_queue()
        q.ensure_group()
        q.publish(1)
        first = q.read_new(count=10, block_ms=0)
        assert len(first) == 1
        # 同一消费者再次读新消息应为空（已投递）
        second = q.read_new(count=10, block_ms=0)
        assert second == []


class TestPendingAndAck:
    def test_pending_before_ack(self):
        q = make_queue()
        q.ensure_group()
        q.publish(7)
        msgs = q.read_new(count=1, block_ms=0)
        assert len(msgs) == 1
        pending = q.message_pending()
        assert pending["pending"] == 1

    def test_ack_clears_pending(self):
        q = make_queue()
        q.ensure_group()
        q.publish(7)
        msgs = q.read_new(count=1, block_ms=0)
        assert q.ack(msgs[0].msg_id) == 1
        assert q.message_pending()["pending"] == 0

    def test_read_pending_returns_unacked(self):
        q = make_queue()
        q.ensure_group()
        q.publish(7)
        q.read_new(count=1, block_ms=0)
        pending = q.read_pending(count=10)
        assert len(pending) == 1
        assert pending[0].job_id == 7


class TestAutoclaim:
    def test_autoclaim_takes_over_orphan(self):
        q = make_queue()
        q.ensure_group()
        q.publish(99)
        q.read_new(count=1, block_ms=0)  # 当前消费者读取但未 ACK
        # 用另一个消费者名接管 min_idle=0 的 pending 消息
        orphan = q.autoclaim(consumer="recovery-worker", min_idle_ms=0, count=10)
        assert len(orphan) == 1
        assert orphan[0].job_id == 99


class TestPayloadEdgeCases:
    def test_bad_json_payload(self):
        q = make_queue()
        q.ensure_group()
        # 直接写坏 payload
        q.client.xadd(STREAM, {"job_id": "5", "data": "not-json"})
        msgs = q.read_new(count=1, block_ms=0)
        assert msgs[0].job_id == 5
        assert msgs[0].payload == {}

    def test_constants(self):
        assert STREAM == "newsagg:site_jobs"
        assert GROUP == "newsagg-workers"
