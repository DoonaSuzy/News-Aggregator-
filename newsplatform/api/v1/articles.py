"""文章查询接口。

- ``GET /articles``：分页列表（多条件过滤），返回不含正文。
- ``GET /articles/{id}``：单篇详情，返回正文。
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from newsplatform.core.deps import DbSession, OptionalSubject
from newsplatform.core.responses import ApiResponse, ok
from newsplatform.schemas.article import ArticleOut
from newsplatform.schemas.common import Page
from newsplatform.services.article_service import ArticleService

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[Page[ArticleOut]],
    summary="文章列表",
    description=(
        "按省份/来源/关键词/日期等条件分页查询文章（北京时间）。"
        "列表不含正文，详情请调 ``/articles/{id}``。"
    ),
)
async def list_articles(
    db: DbSession,
    province: Annotated[Optional[str], Query(description="省份名称或两位代码，如 江苏 或 32")] = None,
    adapter: Annotated[Optional[str], Query(description="来源 adapter_name")] = None,
    keyword: Annotated[Optional[str], Query(description="标题关键词")] = None,
    source_name: Annotated[Optional[str], Query(description="原文来源名称")] = None,
    date_from: Annotated[Optional[str], Query(alias="from", description="起始日期 YYYY-MM-DD")] = None,
    date_to: Annotated[Optional[str], Query(description="结束日期 YYYY-MM-DD")] = None,
    has_time: Annotated[Optional[bool], Query(description="是否仅有发布时间")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResponse:
    page_data = await ArticleService(db).list_articles(
        province=province, adapter=adapter, keyword=keyword,
        source_name=source_name, date_from=date_from, date_to=date_to,
        has_time=has_time, page=page, page_size=page_size,
    )
    return ok(page_data.model_dump())


@router.get(
    "/{article_id}",
    response_model=ApiResponse[ArticleOut],
    summary="文章详情",
    description="按 id 获取单篇文章，含正文纯文本。",
    responses={404: {"description": "文章不存在"}},
)
async def get_article(
    article_id: int,
    db: DbSession,
    subject: OptionalSubject = None,
) -> ApiResponse:
    article = await ArticleService(db).get_article(article_id)
    return ok(article.model_dump())


__all__ = ["router"]
