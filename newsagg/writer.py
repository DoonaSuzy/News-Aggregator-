"""文章写入：落库（upsert）+ 返回投递分类。

文章身份 = source_id + url_hash。重复时比较 content_hash：
- 相同 → 不写（返回 skipped）
- 不同 → 更新正文、时间、updated_at
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from newsagg.db import Database


@dataclass
class ArticleRecord:
    source_id: int
    url_hash: str
    url: str
    title: str
    paragraphs: list[str]
    source_name: str = ""
    published_utc: datetime | None = None
    published_cst: datetime | None = None
    time_precision: str = "unknown"
    content_hash: str = ""
    quality_flags: list[str] | None = None


@dataclass
class WriteResult:
    outcome: str  # "saved" | "updated" | "skipped"
    article_id: int | None = None


class ArticleWriter:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def upsert(self, rec: ArticleRecord) -> WriteResult:
        body = "\n".join(rec.paragraphs)
        flags = json.dumps(rec.quality_flags or [], ensure_ascii=False)
        conn = self.db.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, content_hash FROM articles "
                    "WHERE source_id = %s AND url_hash = %s",
                    (rec.source_id, rec.url_hash),
                )
                existing = cur.fetchone()
                if existing:
                    if existing["content_hash"] == rec.content_hash:
                        return WriteResult("skipped", existing["id"])
                    cur.execute(
                        "UPDATE articles SET url=%s, title=%s, body_text=%s, "
                        "source_name=%s, published_at_utc=%s, published_at_cst=%s, "
                        "time_precision=%s, content_hash=%s, quality_flags=%s, "
                        "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                        (rec.url, rec.title, body, rec.source_name,
                         rec.published_utc, rec.published_cst, rec.time_precision,
                         rec.content_hash, flags, existing["id"]),
                    )
                    conn.commit()
                    return WriteResult("updated", existing["id"])

                cur.execute(
                    "INSERT INTO articles "
                    "(source_id, url_hash, url, title, body_text, source_name, "
                    "published_at_utc, published_at_cst, time_precision, "
                    "content_hash, quality_flags) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rec.source_id, rec.url_hash, rec.url, rec.title, body,
                     rec.source_name, rec.published_utc, rec.published_cst,
                     rec.time_precision, rec.content_hash, flags),
                )
                article_id = cur.lastrowid
            conn.commit()
            return WriteResult("saved", int(article_id))
        finally:
            conn.close()


__all__ = ["ArticleRecord", "WriteResult", "ArticleWriter"]
