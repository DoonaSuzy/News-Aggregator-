"""来源、省份、统计业务逻辑。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from newsplatform.repositories.article_repo import (
    ProvinceRepository, SourceRepository, StatsRepository,
)
from newsplatform.schemas.source import OverviewOut, ProvinceOut, SourceOut


class SourceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SourceRepository(session)

    async def list_sources(self, status=None) -> list[SourceOut]:
        rows = await self.repo.list(status=status)
        return [
            SourceOut(
                id=s.id, adapter_name=s.adapter_name, media_name=s.media_name,
                province_code=s.province_code,
                province_name=s.province.name if s.province else None,
                column_url=s.column_url, status=s.status,
                article_count=s.article_count, last_sync_at_cst=s.last_sync_at_utc,
            )
            for s in rows
        ]


class ProvinceService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ProvinceRepository(session)

    async def list_provinces(self) -> list[ProvinceOut]:
        rows = await self.repo.list_with_counts()
        return [
            ProvinceOut(code=p.code, name=p.name, source_count=int(src or 0),
                        article_count=int(art or 0))
            for p, src, art in rows
        ]


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = StatsRepository(session)

    async def overview(self) -> OverviewOut:
        return OverviewOut(
            total_articles=await self.repo.total_articles(),
            total_sources=await self.repo.total_sources(),
            enabled_sources=await self.repo.total_sources(status="enabled"),
            total_provinces=await self.repo.total_provinces(),
            provinces_with_data=await self.repo.provinces_with_data(),
            latest_article_at_cst=await self.repo.latest_article_at(),
        )


__all__ = ["SourceService", "ProvinceService", "StatsService"]
