"""文章检索：按省份/日期/关键词/时间未知筛选 + 分页。

所有时间过滤基于北京时间 ``published_at_cst`` 墙钟列。``unknown_time``
筛选 ``time_precision = 'unknown'`` 的文章（日期未确认）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from newsagg.db import Database
from newsagg.provinces import resolve_province

#: CSV/展示用的列顺序
COLUMNS = [
    "id", "province_code", "province_name", "adapter_name", "media_name",
    "title", "url", "published_at_cst", "time_precision", "source_name",
    "quality_flags", "body_text",
]


@dataclass
class ArticleFilter:
    """检索条件。"""

    province: str | None = None  # 代码或名称
    day: str | None = None  # YYYY-MM-DD（按北京时间当天）
    keyword: str | None = None  # 标题或正文包含
    unknown_time: bool = False  # 仅日期未确认
    limit: int = 50
    offset: int = 0


def parse_day(value: str) -> tuple[datetime, datetime]:
    """把 ``YYYY-MM-DD`` 解析为北京时间当天的 [start, end) 墙钟区间。"""
    d = date.fromisoformat(value)
    start = datetime(d.year, d.month, d.day, 0, 0, 0)
    end = datetime(d.year, d.month, d.day, 23, 59, 59)
    return start, end


def format_cst(value: datetime | None) -> str:
    """格式化北京时间墙钟为字符串。"""
    if value is None:
        return ""
    return value.isoformat(sep=" ")


def flags_text(flags) -> str:
    """把 quality_flags（JSON/list）渲染为可读文本。"""
    import json

    if isinstance(flags, str):
        try:
            flags = json.loads(flags)
        except (ValueError, TypeError):
            return flags
    if isinstance(flags, (list, tuple)):
        return "; ".join(str(f) for f in flags) or "正常"
    return str(flags) if flags else "正常"


class ArticleQuery:
    """围绕文章表的检索门面。"""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def matching_ids(self, conn, flt: ArticleFilter) -> list[int]:
        """按条件返回命中的文章 id（有序，供分页）。"""
        sql, params = self._build(flt, select_ids=True)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [int(r["id"]) for r in cur.fetchall()]

    def count(self, conn, flt: ArticleFilter) -> int:
        sql, params = self._build(flt, select_ids=False, count=True)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.fetchone()["n"])

    def fetch_ids(self, conn, ids: list[int]) -> list[dict]:
        """按 id 取完整行（保持给定顺序）。"""
        if not ids:
            return []
        placeholders = ",".join(["%s"] * len(ids))
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(COLUMNS)} FROM articles WHERE id IN ({placeholders})",
                ids,
            )
            rows = {int(r["id"]): r for r in cur.fetchall()}
        return [rows[i] for i in ids if i in rows]

    def search_articles(self, conn, flt: ArticleFilter) -> tuple[list[dict], int]:
        """执行检索，返回 (本页行, 总命中数)。"""
        total = self.count(conn, flt)
        ids = self.matching_ids(conn, flt)
        page_ids = ids[flt.offset: flt.offset + flt.limit]
        return self.fetch_ids(conn, page_ids), total

    def get_article(self, conn, article_id: int) -> dict | None:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(COLUMNS)} FROM articles WHERE id = %s",
                (article_id,),
            )
            return cur.fetchone()

    def _build(self, flt: ArticleFilter, *, select_ids: bool,
               count: bool = False) -> tuple[str, list]:
        where: list[str] = []
        params: list = []

        if flt.province:
            code = resolve_province(flt.province)
            if code:
                where.append("s.province_code = %s")
                params.append(code)
        if flt.day:
            start, end = parse_day(flt.day)
            where.append("a.published_at_cst BETWEEN %s AND %s")
            params.extend([start, end])
        if flt.keyword:
            where.append("(a.title LIKE %s OR a.body_text LIKE %s)")
            like = f"%{flt.keyword}%"
            params.extend([like, like])
        if flt.unknown_time:
            where.append("a.time_precision = 'unknown'")

        clause = (" WHERE " + " AND ".join(where)) if where else ""
        if count:
            sql = (
                "SELECT COUNT(*) AS n FROM articles a "
                "JOIN sources s ON s.id = a.source_id " + clause
            )
            return sql, params

        if select_ids:
            sql = (
                "SELECT a.id FROM articles a "
                "JOIN sources s ON s.id = a.source_id " + clause +
                " ORDER BY a.published_at_cst DESC, a.id"
            )
            if flt.limit:
                sql += " LIMIT %s OFFSET %s"
                params.extend([flt.limit, flt.offset])
            return sql, params

        # 直接取行（未分页列投影场景保留）
        sql = (
            "SELECT a.id FROM articles a "
            "JOIN sources s ON s.id = a.source_id " + clause +
            " ORDER BY a.published_at_cst DESC, a.id"
        )
        return sql, params


def search_articles(flt: ArticleFilter, *, db: Database | None = None
                    ) -> tuple[list[dict], int]:
    """便捷函数：一次性连接执行检索。"""
    q = ArticleQuery(db)
    conn = q.db.connect()
    try:
        return q.search_articles(conn, flt)
    finally:
        conn.close()


def get_article(article_id: int, *, db: Database | None = None) -> dict | None:
    q = ArticleQuery(db)
    conn = q.db.connect()
    try:
        return q.get_article(conn, article_id)
    finally:
        conn.close()


__all__ = [
    "ArticleFilter",
    "ArticleQuery",
    "COLUMNS",
    "parse_day",
    "format_cst",
    "flags_text",
    "search_articles",
    "get_article",
]
