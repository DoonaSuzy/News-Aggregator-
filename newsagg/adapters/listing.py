"""列表辅助：置顶识别与倒序判定。"""

from __future__ import annotations

import re
from datetime import datetime

from newsagg.adapters.base import ListItem, ListParse

_STICKY_HINTS = ("置顶", "头条", "sticky", "top")


def mark_sticky(items: list[ListItem]) -> list[ListItem]:
    """标记疑似置顶稿（标题/类名含置顶提示）。"""
    for item in items:
        if any(hint in item.title for hint in _STICKY_HINTS):
            item.sticky = True
    return items


_DATE_IN_TEXT = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")


def _extract_date(text: str) -> datetime | None:
    match = _DATE_IN_TEXT.search(text or "")
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def is_descending(items: list[ListItem]) -> bool:
    """根据列表时间文本判断是否按时间倒序（默认视为倒序）。"""
    dates = [d for d in (_extract_date(i.list_time_text) for i in items) if d]
    if len(dates) < 2:
        return True
    return dates[0] >= dates[-1]


def finalize_list(items: list[ListItem], next_url: str | None = None) -> ListParse:
    """便捷构造 ListParse。"""
    mark_sticky(items)
    return ListParse(items=items, next_url=next_url, descending=is_descending(items))


__all__ = ["mark_sticky", "is_descending", "finalize_list"]
