"""MIME / 页面类型分类：识别可解析文本页与非文本页。"""

from __future__ import annotations

# 视为「非文本」的媒体内容特征
_MEDIA_HINTS = (
    "video", "live", "photo", "picture", "image", "直播", "视频", "图集",
)


def is_non_text_page(url: str, html: str | None) -> bool:
    """启发式判断详情页是否为纯媒体（无法产出正文）。"""
    if url and any(hint in url.lower() for hint in _MEDIA_HINTS):
        return True
    return False


__all__ = ["is_non_text_page"]
