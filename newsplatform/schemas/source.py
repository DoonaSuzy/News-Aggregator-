"""来源与统计相关响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SourceOut(BaseModel):
    id: int
    adapter_name: str
    media_name: str
    province_code: Optional[str] = None
    province_name: Optional[str] = None
    column_url: str = ""
    status: str
    article_count: int = 0
    last_sync_at_cst: Optional[datetime] = None


class ProvinceOut(BaseModel):
    code: str
    name: str
    source_count: int = 0
    article_count: int = 0


class OverviewOut(BaseModel):
    total_articles: int
    total_sources: int
    enabled_sources: int
    total_provinces: int
    provinces_with_data: int
    latest_article_at_cst: Optional[datetime] = None


__all__ = ["SourceOut", "ProvinceOut", "OverviewOut"]
