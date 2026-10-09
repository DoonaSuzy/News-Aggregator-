"""文章查询业务逻辑。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from newsplatform.core.exceptions import NotFound
from newsplatform.models.orm import Article
from newsplatform.provinces import resolve_province
from newsplatform.repositories.article_repo import ArticleRepository
from newsplatform.schemas.article import ArticleOut
from newsplatform.schemas.common import Page, PageMeta


def _parse_date(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        from newsplatform.core.exceptions import BadRequest
        raise BadRequest(f"日期格式应为 YYYY-MM-DD: {text!r}") from exc


def _to_out(article: Article, *, include_body: bool = False) -> ArticleOut:
    flags: List[str] = []
    if article.quality_flags:
        try:
            parsed = json.loads(article.quality_flags)
            if isinstance(parsed, list):
                flags = [str(f) for f in parsed]
        except (ValueError, TypeError):
            flags = []
    src = article.source
    province = src.province if src else None
    return ArticleOut(
        id=article.id,
        source_id=article.source_id,
        province_code=src.province_code if src else None,
        province_name=province.name if province else None,
        media_name=src.media_name if src else None,
        adapter_name=src.adapter_name if src else None,
        title=article.title,
        url=article.url,
        source_name=article.source_name,
        published_at_cst=article.published_at_cst,
        time_precision=article.time_precision,
        quality_flags=flags,
        body_text=article.body_text if include_body else None,
    )


class ArticleService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ArticleRepository(session)

    async def list_articles(self, *, province: Optional[str], adapter: Optional[str],
                            keyword: Optional[str], source_name: Optional[str],
                            date_from: Optional[str], date_to: Optional[str],
                            has_time: Optional[bool], page: int,
                            page_size: int) -> Page[ArticleOut]:
        province_code = resolve_province(province) if province else None
        if province and province_code is None:
            from newsplatform.core.exceptions import BadRequest
            raise BadRequest(f"无法识别的省份: {province!r}")
        filters: Dict[str, Any] = {
            "province": province_code,
            "adapter": adapter,
            "keyword": keyword,
            "source_name": source_name,
            "start": _parse_date(date_from),
            "end": _parse_date(date_to),
            "has_time": has_time,
        }
        total = await self.repo.count(**filters)
        rows = await self.repo.list(page=page, page_size=page_size, **filters)
        items = [_to_out(a, include_body=False) for a in rows]
        pages = (total + page_size - 1) // page_size if page_size else 0
        return Page(items=items, meta=PageMeta(
            total=total, page=page, page_size=page_size, pages=pages))

    async def get_article(self, article_id: int) -> ArticleOut:
        article = await self.repo.get(article_id)
        if article is None:
            raise NotFound(f"文章不存在: {article_id}")
        return _to_out(article, include_body=True)


__all__ = ["ArticleService"]
