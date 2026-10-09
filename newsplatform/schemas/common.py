"""通用分页与查询模型。"""

from __future__ import annotations

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageMeta(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20
    pages: int = 0


class Page(BaseModel, Generic[T]):
    items: List[T] = Field(default_factory=list)
    meta: PageMeta


class PageParams(BaseModel):
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(20, ge=1, le=100, description="每页条数，最大 100")


__all__ = ["PageMeta", "Page", "PageParams"]
