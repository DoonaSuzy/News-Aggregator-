"""文章相关请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ArticleOut(BaseModel):
    id: int
    source_id: int
    province_code: Optional[str] = None
    province_name: Optional[str] = None
    media_name: Optional[str] = None
    adapter_name: Optional[str] = None
    title: str = ""
    url: str
    source_name: str = ""
    published_at_cst: Optional[datetime] = None
    time_precision: str = "unknown"
    quality_flags: List[str] = Field(default_factory=list)
    # 详情接口才返回正文，列表接口不含
    body_text: Optional[str] = None


class ArticleQuery(BaseModel):
    province: Optional[str] = Field(None, description="省份名称或两位代码")
    adapter: Optional[str] = Field(None, description="来源 adapter_name")
    keyword: Optional[str] = Field(None, description="标题关键词")
    source_name: Optional[str] = Field(None, description="原文来源名称")
    from_: Optional[str] = Field(None, alias="from", description="起始日期 YYYY-MM-DD（北京时间）")
    to: Optional[str] = Field(None, description="结束日期 YYYY-MM-DD（北京时间）")
    has_time: Optional[bool] = Field(None, description="是否有发布时间")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    model_config = {"populate_by_name": True}


__all__ = ["ArticleOut", "ArticleQuery"]
