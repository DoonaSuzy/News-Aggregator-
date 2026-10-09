"""抓取期去重：URL 布隆过滤器 + 多源同文检测。

两类能力：

1. **URL 布隆过滤器（跨任务持久）**
   用 Redis 位图（``SETBIT``/``GETBIT``）实现跨任务运行期的 URL 判重。
   已完整抓取过的详情页，在后续批次里可直接跳过 HTTP 请求，减少重复抓取。
   位图大小与哈希数固定，误判率由容量决定（非精确集合，允许少量假阳性）。

2. **多源同文检测**
   同一新闻被多个省级站点转载时，``content_hash`` 相同但 ``source_id`` 不同。
   ``find_duplicate()`` 跨来源按 ``content_hash`` 查找首发文章，用于在
   ``quality_flags`` 打 ``duplicate_of`` 标记，而非物理删除（保留各来源记录）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import redis

#: 布隆位图位数（2^24 ≈ 1677 万位 ≈ 2MB），k 个哈希从 url_hash 派生
_BLOOM_BITS = 1 << 24
#: 派生哈希个数（越大误判率越低，位图读取次数越多）
_BLOOM_HASHES = 4
#: 已抓取 URL 的布隆键
BLOOM_KEY = "newsagg:bloom:seen"


def _bit_positions(token: str) -> list[int]:
    """从一个十六进制 token（如 url_hash）派生 k 个位下标。

    url_hash 已是 SHA-256 十六进制（64 字符），按 8 字符切片取模得到独立位下标，
    无需额外哈希函数。
    """
    positions: list[int] = []
    for i in range(_BLOOM_HASHES):
        chunk = token[(i * 8) % len(token):][:8] if len(token) >= 8 else token
        if len(chunk) < 8:
            chunk = (chunk + token)[:8]
        positions.append(int(chunk, 16) % _BLOOM_BITS)
    return positions


class UrlBloom:
    """基于 Redis 位图的布隆过滤器。

    - ``maybe_seen``：可能已见（含假阳性）；用于抓取前跳过请求。
    - ``add``：抓取成功后标记为已见。
    - 误判不影响正确性——真正的去重仍由 DB 唯一键兜底。
    """

    def __init__(self, client: "redis.Redis", *, key: str = BLOOM_KEY) -> None:
        self._client = client
        self._key = key

    def maybe_seen(self, url_hash: str) -> bool:
        """若所有位均为 1，返回 True（可能已见过）。"""
        pipe = self._client.pipeline(transaction=False)
        for pos in _bit_positions(url_hash):
            pipe.getbit(self._key, pos)
        bits = pipe.execute()
        return all(bool(b) for b in bits)

    def add(self, url_hash: str) -> None:
        """标记一个 url_hash 为已见。"""
        pipe = self._client.pipeline(transaction=False)
        for pos in _bit_positions(url_hash):
            pipe.setbit(self._key, pos, 1)
        pipe.execute()

    def seen_or_add(self, url_hash: str) -> bool:
        """先判后加：已见返回 True（跳过抓取），未见则标记并返回 False。"""
        if self.maybe_seen(url_hash):
            return True
        self.add(url_hash)
        return False


def find_duplicate_article(conn, *, source_id: int, content_hash: str,
                           exclude_article_id: int | None = None):
    """跨来源查找与 ``content_hash`` 相同的既有文章（首发来源）。

    返回命中行（含 id / adapter_name / province_code），无则返回 None。
    内容为空哈希时不查。
    """
    if not content_hash:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.id, a.source_id, s.adapter_name, s.province_code "
            "FROM articles a JOIN sources s ON s.id = a.source_id "
            "WHERE a.content_hash = %s AND a.source_id <> %s "
            "  AND (%s IS NULL OR a.id <> %s) "
            "ORDER BY a.id ASC LIMIT 1",
            (content_hash, source_id, exclude_article_id, exclude_article_id),
        )
        return cur.fetchone()


__all__ = [
    "UrlBloom",
    "find_duplicate_article",
    "BLOOM_KEY",
]
