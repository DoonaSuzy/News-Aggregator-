"""Redis Stream 队列封装。

流名 ``newsagg:site_jobs``，消费组 ``newsagg-workers``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import redis

from newsagg.config import get_settings

STREAM = "newsagg:site_jobs"
GROUP = "newsagg-workers"


@dataclass
class Message:
    """一条队列消息。"""

    msg_id: str
    job_id: int
    payload: dict[str, Any]


class StreamQueue:
    def __init__(self, url: str | None = None, *, client: "redis.Redis | None" = None) -> None:
        if client is not None:
            self._url = "injected"
            self._client = client
            return
        self._url = url or get_settings().redis_url
        # protocol=2 兼容 RESP2 旧版服务器（Redis 3.x / Memurai）
        self._client = redis.Redis.from_url(self._url, decode_responses=True, protocol=2)

    @property
    def client(self) -> redis.Redis:
        return self._client

    def ensure_group(self) -> None:
        """确保消费组存在（已存在则忽略 BUSYGROUP）。"""
        try:
            self._client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def publish(self, job_id: int, payload: dict[str, Any] | None = None) -> str:
        """投递一个站点任务，返回消息 id。"""
        body = {"job_id": str(job_id), "data": json.dumps(payload or {}, ensure_ascii=False)}
        return self._client.xadd(STREAM, body)

    def read_new(self, count: int = 1, block_ms: int = 5000) -> list[Message]:
        """读取尚未投递给本组的新消息（``>``）。"""
        resp = self._client.xreadgroup(GROUP, self._consumer(), {STREAM: ">"}, count=count, block=block_ms)
        return self._parse(resp)

    def read_pending(self, count: int = 10) -> list[Message]:
        """读取本组已投递但未 ACK 的消息（不含新消息）。"""
        resp = self._client.xreadgroup(GROUP, self._consumer(), {STREAM: "0"}, count=count)
        return self._parse(resp)

    def autoclaim(self, consumer: str, min_idle_ms: int = 60000, count: int = 10) -> list[Message]:
        """接管其他崩溃消费者遗留的 pending 消息。

        优先使用 XAUTOCLAIM（Redis 6.2+）；若服务器不支持，
        回退到 XPENDING 扫描 + XCLAIM（Redis 5.0+ 等价实现）。
        """
        try:
            resp = self._client.xautoclaim(
                STREAM, GROUP, consumer, min_idle_time=min_idle_ms, start_id="0-0", count=count
            )
            entries = resp[1] if resp and len(resp) >= 2 else []
            return [self._to_message(mid, fields) for mid, fields in entries]
        except redis.ResponseError as exc:
            if "unknown command" not in str(exc).lower():
                raise
            return self._autoclaim_fallback(consumer, min_idle_ms, count)

    def _autoclaim_fallback(self, consumer: str, min_idle_ms: int, count: int) -> list[Message]:
        """Redis 5.0 兼容的接管实现。"""
        claimed: list[Message] = []
        # 分页扫描整个 pending 列表
        start = "-"
        range_count = max(count, 100)
        while len(claimed) < count:
            page = self._client.xpending_range(STREAM, GROUP, min=start, max="+", count=range_count)
            if not page:
                break
            idle_ids = [
                entry["message_id"]
                for entry in page
                if entry.get("time_since_delivered", 0) >= min_idle_ms
            ]
            if idle_ids:
                # XCLAIM 接管这些消息到本消费者
                result = self._client.xclaim(STREAM, GROUP, consumer, 0, idle_ids)
                for mid, fields in result:
                    claimed.append(self._to_message(mid, fields))
                    if len(claimed) >= count:
                        break
            # 前进到下一页；若本页无更多则退出
            last_id = page[-1]["message_id"]
            if start == last_id or len(page) < range_count:
                break
            start = last_id
            # xpending_range 的 min 是闭区间，用 ( 前缀排除已处理
            start = "(" + last_id
        return claimed

    def ack(self, msg_id: str) -> int:
        """确认消息已处理。"""
        return self._client.xack(STREAM, GROUP, msg_id)

    def message_pending(self) -> dict[str, int]:
        """返回 pending 概览。"""
        summary = self._client.xpending(STREAM, GROUP)
        return {"pending": summary.get("pending", 0) if isinstance(summary, dict) else 0}

    def _consumer(self) -> str:
        import os
        import socket
        return f"{socket.gethostname()}-{os.getpid()}"

    def _parse(self, resp: Any) -> list[Message]:
        messages: list[Message] = []
        if not resp:
            return messages
        for _stream, entries in resp:
            for mid, fields in entries:
                messages.append(self._to_message(mid, fields))
        return messages

    @staticmethod
    def _to_message(mid: str, fields: dict[str, Any]) -> Message:
        job_id = int(fields.get("job_id", "0"))
        raw = fields.get("data", "{}")
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            payload = {}
        return Message(msg_id=mid, job_id=job_id, payload=payload)


__all__ = ["StreamQueue", "Message", "STREAM", "GROUP"]
