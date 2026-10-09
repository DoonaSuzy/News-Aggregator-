"""文章检索：按省份/日期区间/关键词/时间未知筛选 + 分页。

所有时间过滤基于北京时间 ``published_at_cst`` 墙钟列。``unknown_time``
筛选 ``time_precision = 'unknown'`` 的文章（日期未确认）。

日期条件三种写法（``day`` 为单日兼容别名）：
- ``day``：命中北京时间当天；
- ``date_from`` / ``date_to``：闭区间（含首尾两天 00:00:00–23:59:59）。

``build_where()`` 把筛选条件编译成 WHERE 子句，检索与 CSV 导出共用，
保证两种入口过滤语义一致。
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
    day: str | None = None  # YYYY-MM-DD（按北京时间当天；单日兼容别名）
    date_from: str | None = None  # YYYY-MM-DD（含当天 00:00 起）
    date_to: str | None = None  # YYYY-MM-DD（含当天 23:59:59 止）
    keyword: str | None = None  # 关键词包含（body_only 时仅正文）
    body_only: bool = False  # 关键词仅匹配正文
    unknown_time: bool = False  # 仅日期未确认
    limit: int = 50
    offset: int = 0


def parse_day(value: str) -> tuple[datetime, datetime]:
    """把 ``YYYY-MM-DD`` 解析为北京时间当天的墙钟闭区间 [00:00:00, 23:59:59]。"""
    d = date.fromisoformat(value)
    start = datetime(d.year, d.month, d.day, 0, 0, 0)
    end = datetime(d.year, d.month, d.day, 23, 59, 59)
    return start, end


def _day_start(value: str) -> datetime:
    d = date.fromisoformat(value)
    return datetime(d.year, d.month, d.day, 0, 0, 0)


def _day_end(value: str) -> datetime:
    d = date.fromisoformat(value)
    return datetime(d.year, d.month, d.day, 23, 59, 59)


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


def build_where(flt: ArticleFilter) -> tuple[str, list]:
    """把筛选条件编译成 ``WHERE`` 子句与参数（检索/导出共用）。

    返回 ``(clause, params)``；无条件时 ``clause`` 为空串。
    """
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
    if flt.date_from:
        where.append("a.published_at_cst >= %s")
        params.append(_day_start(flt.date_from))
    if flt.date_to:
        where.append("a.published_at_cst <= %s")
        params.append(_day_end(flt.date_to))
    if flt.keyword:
        like = f"%{flt.keyword}%"
        if flt.body_only:
            where.append("a.body_text LIKE %s")
            params.append(like)
        else:
            where.append("(a.title LIKE %s OR a.body_text LIKE %s)")
            params.extend([like, like])
    if flt.unknown_time:
        where.append("a.time_precision = 'unknown'")

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    return clause, params


class ArticleQuery:
    """围绕文章表的检索门面。"""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def matching_ids(self, conn, flt: ArticleFilter) -> list[int]:
        """按条件返回命中的全部文章 id（有序，供分页切片）。"""
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
        """执行检索，返回 (本页行, 总命中数)。

        分页只在 Python 层做一次切片（SQL 取全部命中 id 后截取
        ``[offset, offset+limit)``），避免 SQL 与切片双重分页。
        """
        total = self.count(conn, flt)
        ids = self.matching_ids(conn, flt)
        page_ids = ids[flt.offset: flt.offset + flt.limit] if flt.limit else ids
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
        clause, params = build_where(flt)
        if count:
            sql = (
                "SELECT COUNT(*) AS n FROM articles a "
                "JOIN sources s ON s.id = a.source_id" + clause
            )
            return sql, params

        # ids / 行查询共用同一排序；分页由调用方在 Python 层切片
        sql = (
            "SELECT a.id FROM articles a "
            "JOIN sources s ON s.id = a.source_id" + clause +
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
    "build_where",
    "parse_day",
    "format_cst",
    "flags_text",
    "search_articles",
    "get_article",
]
