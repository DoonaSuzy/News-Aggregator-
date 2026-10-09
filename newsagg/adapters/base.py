"""适配器协议与数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ListItem:
    """列表页发现的一条候选。"""

    url: str
    title: str = ""
    list_time_text: str = ""
    sticky: bool = False


@dataclass
class ListParse:
    """列表解析结果。"""

    items: list[ListItem] = field(default_factory=list)
    #: 下一页 URL（无则 None）
    next_url: str | None = None
    #: 列表是否按时间倒序
    descending: bool = True


@dataclass
class DetailParse:
    """详情页解析结果。"""

    title: str = ""
    paragraphs: list[str] = field(default_factory=list)
    source_name: str = ""
    published_text: str = ""
    #: 是否为纯媒体（图片/视频/直播），无实质文字
    media_only: bool = False


@runtime_checkable
class SiteAdapter(Protocol):
    """站点适配器协议。"""

    name: str
    version: str
    allowed_hosts: tuple[str, ...]
    column_url: str

    def allows(self, url: str) -> bool: ...

    def is_article(self, url: str) -> bool: ...

    def parse_list(self, html: str, *, base_url: str) -> ListParse: ...

    def parse_detail(self, html: str, *, url: str) -> DetailParse: ...


__all__ = ["ListItem", "ListParse", "DetailParse", "SiteAdapter"]
