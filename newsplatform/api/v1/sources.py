"""来源、省份与统计接口。"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Query

from newsplatform.core.deps import DbSession
from newsplatform.core.responses import ApiResponse, ok
from newsplatform.schemas.source import OverviewOut, ProvinceOut, SourceOut
from newsplatform.services.source_service import ProvinceService, SourceService, StatsService

router = APIRouter()


@router.get(
    "/sources",
    response_model=ApiResponse[list[SourceOut]],
    summary="来源列表",
    description="列出全部新闻来源，可按状态过滤。",
)
async def list_sources(
    db: DbSession,
    status: Annotated[Optional[str], Query(description="来源状态：enabled/paused/...")] = None,
) -> ApiResponse:
    rows = await SourceService(db).list_sources(status=status)
    return ok([r.model_dump() for r in rows])


@router.get(
    "/provinces",
    response_model=ApiResponse[list[ProvinceOut]],
    summary="省份覆盖",
    description="31 个省级行政区及其来源数、文章数。",
)
async def list_provinces(db: DbSession) -> ApiResponse:
    rows = await ProvinceService(db).list_provinces()
    return ok([r.model_dump() for r in rows])


@router.get(
    "/stats/overview",
    response_model=ApiResponse[OverviewOut],
    summary="总览统计",
    description="文章总数、来源数、覆盖省份数、最新文章时间等概览。",
)
async def overview(db: DbSession) -> ApiResponse:
    data = await StatsService(db).overview()
    return ok(data.model_dump())


__all__ = ["router"]
