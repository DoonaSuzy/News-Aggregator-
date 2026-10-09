"""31 个省级行政区代码表（平台独立，勿依赖爬虫包）。

代码采用 GB/T 2260 两位数字码。
"""

from __future__ import annotations

PROVINCES: tuple[tuple[str, str], ...] = (
    ("11", "北京"), ("12", "天津"), ("13", "河北"), ("14", "山西"),
    ("15", "内蒙古"), ("21", "辽宁"), ("22", "吉林"), ("23", "黑龙江"),
    ("31", "上海"), ("32", "江苏"), ("33", "浙江"), ("34", "安徽"),
    ("35", "福建"), ("36", "江西"), ("37", "山东"), ("41", "河南"),
    ("42", "湖北"), ("43", "湖南"), ("44", "广东"), ("45", "广西"),
    ("46", "海南"), ("50", "重庆"), ("51", "四川"), ("52", "贵州"),
    ("53", "云南"), ("54", "西藏"), ("61", "陕西"), ("62", "甘肃"),
    ("63", "青海"), ("64", "宁夏"), ("65", "新疆"),
)

NAME_TO_CODE = {name: code for code, name in PROVINCES}
CODE_TO_NAME = {code: name for code, name in PROVINCES}


def resolve_province(value: str | None) -> str | None:
    """把省份名称或两位代码解析为两位代码；无法识别返回 None。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in CODE_TO_NAME:
        return text
    if text in NAME_TO_CODE:
        return NAME_TO_CODE[text]
    for suffix in ("省", "市", "壮族自治区", "回族自治区", "维吾尔自治区", "自治区"):
        if text.endswith(suffix):
            trimmed = text[: -len(suffix)]
            if trimmed in NAME_TO_CODE:
                return NAME_TO_CODE[trimmed]
    return None


__all__ = ["PROVINCES", "NAME_TO_CODE", "CODE_TO_NAME", "resolve_province"]
