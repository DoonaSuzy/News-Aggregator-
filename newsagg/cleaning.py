"""文本清洗、时间解析与质量标记。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

# 时间精度
PRECISION_UNKNOWN = "unknown"
PRECISION_DATE = "date"
PRECISION_MINUTE = "minute"
PRECISION_SECOND = "second"

# 质量标记
FLAG_NON_TEXT = "non_text_content"

_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")


def clean_title(title: str | None) -> str:
    """规范化标题：去标签、压缩空白、去零宽字符、限制长度。"""
    if not title:
        return ""
    text = _TAG_RE.sub(" ", title)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = text.replace(" ", " ")
    text = _WS_RE.sub(" ", text).strip()
    # 数据库列为 VARCHAR(512)，按字符截断保护
    return text[:512]


def clean_source(source: str | None) -> str:
    """规范化来源名称。"""
    if not source:
        return ""
    text = _TAG_RE.sub(" ", source)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = text.replace(" ", " ")
    text = _WS_RE.sub(" ", text).strip()
    # 去掉常见的来源前缀
    for prefix in ("来源：", "来源:", "来源 "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text


def clean_paragraphs(paragraphs: list[str] | None) -> list[str]:
    """清洗正文段落列表：去空段、去标签、压缩空白。"""
    if not paragraphs:
        return []
    cleaned: list[str] = []
    for para in paragraphs:
        if para is None:
            continue
        text = _TAG_RE.sub(" ", para)
        text = _ZERO_WIDTH_RE.sub("", text)
        text = text.replace(" ", " ")
        text = _WS_RE.sub(" ", text).strip()
        if text:
            cleaned.append(text)
    return cleaned


def content_hash(paragraphs: list[str]) -> str:
    """正文段落的 SHA-256（用于变更检测）。"""
    joined = "\n".join(paragraphs)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def quality_flags(paragraphs: list[str], *, is_media_only: bool = False) -> list[str]:
    """根据正文生成质量标记列表。"""
    flags: list[str] = []
    total_chars = sum(len(p) for p in paragraphs)
    if is_media_only or total_chars == 0:
        flags.append(FLAG_NON_TEXT)
    return flags


# --- 时间解析 -------------------------------------------------------------

@dataclass(frozen=True)
class ParsedTime:
    """解析结果。``value`` 为北京时间 naive datetime，``precision`` 为精度。"""

    value: datetime | None
    precision: str


_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # 2026-10-03 15:04:05 / 2026/10/3 15:04:05
    (re.compile(r"(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})[ T]"
                r"(?P<H>\d{1,2}):(?P<M>\d{2}):(?P<S>\d{2})"), "y m d H M S", PRECISION_SECOND),
    # 2026-10-03 15:04
    (re.compile(r"(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})[ T]"
                r"(?P<H>\d{1,2}):(?P<M>\d{2})(?!:)"), "y m d H M", PRECISION_MINUTE),
    # 2026-10-03
    (re.compile(r"(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})"), "y m d", PRECISION_DATE),
    # 2026年10月3日 15:04
    (re.compile(r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日\s*"
                r"(?P<H>\d{1,2}):(?P<M>\d{2})"), "y m d H M", PRECISION_MINUTE),
    # 2026年10月3日
    (re.compile(r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日"), "y m d", PRECISION_DATE),
    # 10-03 15:04（无年份，按当前年）
    (re.compile(r"(?P<m>\d{1,2})-(?P<d>\d{1,2})\s+(?P<H>\d{1,2}):(?P<M>\d{2})"), "m d H M", PRECISION_MINUTE),
]


def parse_published(raw: str | None, *, default_year: int | None = None) -> ParsedTime:
    """从原始文本解析发布时间（按北京时间处理，naive）。

    支持 6 种常见格式，返回 ``ParsedTime``。
    """
    if not raw:
        return ParsedTime(None, PRECISION_UNKNOWN)
    text = _TAG_RE.sub(" ", raw)
    text = _WS_RE.sub(" ", text).strip()
    year = default_year or datetime.now().year

    for pattern, fields, precision in _PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        gd = match.groupdict()
        try:
            y = int(gd.get("y", year)) if "y" in fields else year
            m = int(gd["m"])
            d = int(gd["d"])
            H = int(gd["H"]) if "H" in fields else 0
            M = int(gd["M"]) if "M" in fields else 0
            S = int(gd["S"]) if "S" in fields else 0
            value = datetime(y, m, d, H, M, S)
            return ParsedTime(value, precision)
        except (ValueError, KeyError):
            continue
    return ParsedTime(None, PRECISION_UNKNOWN)


# --- CSV 防公式注入 --------------------------------------------------------

def csv_cell(value: object) -> str:
    """转义 CSV 单元格，防止表格软件把内容当公式。"""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def to_utc_naive(cst_naive: datetime) -> datetime:
    """北京时间 naive → UTC naive（北京 = UTC+8，不含夏令时）。"""
    from datetime import timedelta

    return cst_naive - timedelta(hours=8)


def to_cst_naive(utc_naive: datetime) -> datetime:
    """UTC naive → 北京时间 naive。"""
    from datetime import timedelta

    return utc_naive + timedelta(hours=8)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


__all__ = [
    "PRECISION_UNKNOWN",
    "PRECISION_DATE",
    "PRECISION_MINUTE",
    "PRECISION_SECOND",
    "FLAG_NON_TEXT",
    "ParsedTime",
    "clean_title",
    "clean_source",
    "clean_paragraphs",
    "content_hash",
    "quality_flags",
    "parse_published",
    "csv_cell",
    "to_utc_naive",
    "to_cst_naive",
    "utc_now_naive",
]
