"""文章 / 来源 / 统计的数据访问层（async SQLAlchemy）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from newsplatform.models.orm import Article, Province, Source


def _apply_article_filters(stmt: Select, *, province: Optional[str] = None,
                           adapter: Optional[str] = None, keyword: Optional[str] = None,
                           source_name: Optional[str] = None,
                           start: Optional[datetime] = None, end: Optional[datetime] = None,
                           has_time: Optional[bool] = None) -> Select:
    if province:
        # 允许按省份名称或代码过滤
        stmt = stmt.join(Source, Article.source_id == Source.id).where(
            Source.province_code == province
        )
    if adapter:
        stmt = stmt.join(Source, Article.source_id == Source.id).where(
            Source.adapter_name == adapter
        )
    if keyword:
        stmt = stmt.where(Article.title.like(f"%{keyword}%"))
    if source_name:
        stmt = stmt.where(Article.source_name == source_name)
    if start is not None:
        stmt = stmt.where(Article.published_at_cst >= start)
    if end is not None:
        stmt = stmt.where(Article.published_at_cst <= end)
    if has_time is True:
        stmt = stmt.where(Article.published_at_cst.is_not(None))
    elif has_time is False:
        stmt = stmt.where(Article.published_at_cst.is_(None))
    return stmt


class ArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count(self, **filters) -> int:
        stmt = select(func.count()).select_from(Article)
        stmt = _apply_article_filters(stmt, **filters)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def list(self, *, page: int, page_size: int, **filters) -> Sequence[Article]:
        stmt = select(Article).options(selectinload(Article.source))
        stmt = _apply_article_filters(stmt, **filters)
        stmt = stmt.order_by(Article.published_at_cst.desc(), Article.id.desc())
        stmt = stmt.limit(page_size).offset((page - 1) * page_size)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get(self, article_id: int) -> Optional[Article]:
        stmt = select(Article).options(selectinload(Article.source)).where(
            Article.id == article_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, status: Optional[str] = None) -> Sequence[Source]:
        stmt = select(Source).options(selectinload(Source.province))
        if status:
            stmt = stmt.where(Source.status == status)
        stmt = stmt.order_by(Source.province_code, Source.adapter_name)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_username(self, username: str):
        from newsplatform.models.orm import User
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ProvinceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_with_counts(self) -> Sequence[tuple]:
        """返回 (Province, source_count, article_count)。"""
        src_count = (
            select(func.count(func.distinct(Source.id)))
            .where(Source.province_code == Province.code)
            .correlate(Province)
            .scalar_subquery()
        )
        art_count = (
            select(func.count(Article.id))
            .join(Source, Article.source_id == Source.id)
            .where(Source.province_code == Province.code)
            .correlate(Province)
            .scalar_subquery()
        )
        stmt = select(Province, src_count.label("src"), art_count.label("art")).order_by(
            Province.code
        )
        result = await self.session.execute(stmt)
        return result.all()


class StatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _scalar(self, stmt) -> int:
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def total_articles(self) -> int:
        return await self._scalar(select(func.count()).select_from(Article))

    async def total_sources(self, status: Optional[str] = None) -> int:
        stmt = select(func.count()).select_from(Source)
        if status:
            stmt = stmt.where(Source.status == status)
        return await self._scalar(stmt)

    async def total_provinces(self) -> int:
        return await self._scalar(select(func.count()).select_from(Province))

    async def provinces_with_data(self) -> int:
        stmt = (
            select(func.count(func.distinct(Source.province_code)))
            .select_from(Article)
            .join(Source, Article.source_id == Source.id)
            .where(Source.province_code.is_not(None))
        )
        return await self._scalar(stmt)

    async def latest_article_at(self) -> Optional[datetime]:
        result = await self.session.execute(
            select(func.max(Article.published_at_cst))
        )
        return result.scalar_one_or_none()


__all__ = [
    "ArticleRepository", "SourceRepository", "ProvinceRepository", "StatsRepository",
]
