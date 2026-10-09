"""URL 规范化与稳定哈希。

文章身份 = 来源 id + 规范化 URL 的 SHA-256。
规范化只做最小改动：去片段、主机名小写、删 utm_*/spm/from/scene；
未知查询参数保留，不改 http/https。
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

#: 需要剔除的查询参数（前缀匹配）
_DROP_PREFIXES = ("utm_",)
_DROP_EXACT = {"spm", "from", "scene"}


def normalize_url(url: str) -> str:
    """返回规范化后的 URL。"""
    if not url:
        return ""
    url = url.strip()
    parts = urlsplit(url)
    scheme = parts.scheme or "http"
    host = (parts.netloc or "").lower()
    path = parts.path or ""
    # 保留未知查询参数，剔除跟踪参数
    kept: list[tuple[str, str]] = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        low = key.lower()
        if any(low.startswith(p) for p in _DROP_PREFIXES):
            continue
        if low in _DROP_EXACT:
            continue
        kept.append((key, val))
    query = urlencode(kept, doseq=True)
    # 去片段
    return urlunsplit((scheme, host, path, query, ""))


def url_hash(url: str) -> str:
    """规范化 URL 的 SHA-256 十六进制摘要。"""
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


__all__ = ["normalize_url", "url_hash"]
