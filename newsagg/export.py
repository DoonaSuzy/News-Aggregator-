"""文章导出 CSV。

可选传入 :class:`~newsagg.query.ArticleFilter` 按省份/日期区间/关键词筛选
（与 ``query`` 命令共用同一 ``build_where``，语义一致）；不传则导出全表。
"""

from __future__ import annotations

import csv
import os
from typing import TYPE_CHECKING

from newsagg.cleaning import csv_cell
from newsagg.config import get_settings
from newsagg.db import Database

if TYPE_CHECKING:
    from newsagg.query import ArticleFilter

COLUMNS = [
    "id", "province_code", "province_name", "adapter_name", "media_name",
    "title", "url", "published_at_cst", "time_precision", "source_name",
    "quality_flags", "body_text",
]


def export_csv(out_path: str, flt: "ArticleFilter | None" = None) -> str:
    settings = get_settings()
    root = settings.root
    if not os.path.isabs(out_path):
        out_path = os.path.join(str(root), out_path)

    clause, params = ("", [])
    if flt is not None:
        from newsagg.query import build_where

        clause, params = build_where(flt)

    conn = Database().connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT a.id, s.province_code, p.name AS province_name, "
                "s.adapter_name, s.media_name, a.title, a.url, a.published_at_cst, "
                "a.time_precision, a.source_name, a.quality_flags, a.body_text "
                "FROM articles a JOIN sources s ON s.id = a.source_id "
                "LEFT JOIN provinces p ON p.code = s.province_code" + clause +
                " ORDER BY a.published_at_cst DESC, a.id",
                params,
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for r in rows:
            flags = r.get("quality_flags")
            if isinstance(flags, (list, dict)):
                import json
                flags = json.dumps(flags, ensure_ascii=False)
            pub = r.get("published_at_cst")
            writer.writerow([
                csv_cell(r.get("id")),
                csv_cell(r.get("province_code")),
                csv_cell(r.get("province_name")),
                csv_cell(r.get("adapter_name")),
                csv_cell(r.get("media_name")),
                csv_cell(r.get("title")),
                csv_cell(r.get("url")),
                csv_cell(pub.isoformat(sep=" ") if pub else ""),
                csv_cell(r.get("time_precision")),
                csv_cell(r.get("source_name")),
                csv_cell(flags),
                csv_cell(r.get("body_text")),
            ])
    return out_path


__all__ = ["export_csv", "COLUMNS"]
