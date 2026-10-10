"""从本机爬虫库 newsagg 导出数据，生成中台库 newsagg_platform 的导入 SQL。

用法（本机 Windows，MySQL 已运行在 D:/newsagg_mysql_data）::

    python scripts/export_platform_data.py -o newsagg_platform_import.sql

依赖：PyMySQL（已装）。连接用 root 空密码（本机开发库）。
字段映射：
- provinces: code/name 直接拷贝
- sources:  verification_status -> status；last_discovery_success_at_utc -> last_sync_at_utc；
            article_count 由 articles 统计；保留原 id 以对齐 articles.source_id
- articles: 五类字段 + 时间/精度/quality_flags；保留原 id 与 source_id
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = dict(host="127.0.0.1", port=3306, user="root", password="",
           database="newsagg", charset="utf8mb4")

# verification_status -> 中台 status
_STATUS_MAP = {
    "enabled": "enabled",
    "verified": "enabled",
    "candidate": "candidate",
    "paused": "paused",
}


def q(v):
    """SQL 字面量转义。"""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    if hasattr(v, "strftime"):  # datetime
        return "'" + v.strftime("%Y-%m-%d %H:%M:%S") + "'"
    s = str(v).replace("\\", "\\\\").replace("'", "''")
    return "'" + s + "'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="newsagg_platform_import.sql")
    ap.add_argument("--host", default=SRC["host"])
    ap.add_argument("--user", default=SRC["user"])
    ap.add_argument("--password", default=SRC["password"])
    ap.add_argument("--database", default=SRC["database"])
    args = ap.parse_args()

    conn = pymysql.connect(host=args.host, port=SRC["port"], user=args.user,
                           password=args.password, database=args.database,
                           charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    out = ROOT / args.out
    lines: list[str] = [
        "-- 数据中台导入 SQL：由 scripts/export_platform_data.py 从爬虫库 newsagg 生成",
        "-- 目标库：newsagg_platform；在目标 MySQL 上执行：mysql ... newsagg_platform < 本文件",
        "SET NAMES utf8mb4;",
        "SET time_zone = '+00:00';",
        "USE newsagg_platform;",
        "",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "TRUNCATE TABLE articles;",
        "TRUNCATE TABLE sources;",
        "TRUNCATE TABLE provinces;",
        "TRUNCATE TABLE ingest_batches;",
        "SET FOREIGN_KEY_CHECKS = 1;",
        "",
    ]

    with conn:
        cur = conn.cursor()
        # provinces
        cur.execute("SELECT code, name FROM provinces ORDER BY code")
        provinces = cur.fetchall()
        lines.append("-- provinces")
        for p in provinces:
            lines.append(
                f"INSERT INTO provinces (code, name) VALUES ({q(p['code'])}, {q(p['name'])});"
            )
        lines.append("")

        # 每来源文章数
        cur.execute("SELECT source_id, COUNT(*) c FROM articles GROUP BY source_id")
        art_count = {r["source_id"]: r["c"] for r in cur.fetchall()}

        # sources
        cur.execute(
            "SELECT id, adapter_name, province_code, media_name, column_url, "
            "verification_status, last_discovery_success_at_utc FROM sources ORDER BY id"
        )
        sources = cur.fetchall()
        lines.append("-- sources")
        for s in sources:
            status = _STATUS_MAP.get(s["verification_status"], "candidate")
            lines.append(
                "INSERT INTO sources (id, adapter_name, media_name, province_code, "
                "column_url, status, article_count, last_sync_at_utc) VALUES ("
                f"{s['id']}, {q(s['adapter_name'])}, {q(s['media_name'])}, "
                f"{q(s['province_code'])}, {q(s['column_url'])}, {q(status)}, "
                f"{art_count.get(s['id'], 0)}, {q(s['last_discovery_success_at_utc'])});"
            )
        lines.append("")

        # articles（分批，避免单条 SQL 过大）
        cur.execute(
            "SELECT id, source_id, url_hash, url, title, body_text, source_name, "
            "published_at_utc, published_at_cst, time_precision, content_hash, "
            "quality_flags FROM articles ORDER BY id"
        )
        lines.append("-- articles")
        n = 0
        for a in cur:
            flags = a["quality_flags"]
            if isinstance(flags, (list, dict)):
                import json
                flags = json.dumps(flags, ensure_ascii=False)
            lines.append(
                "INSERT INTO articles (id, source_id, url_hash, url, title, body_text, "
                "source_name, published_at_utc, published_at_cst, time_precision, "
                "content_hash, quality_flags) VALUES ("
                f"{a['id']}, {a['source_id']}, {q(a['url_hash'])}, {q(a['url'])}, "
                f"{q(a['title'])}, {q(a['body_text'])}, {q(a['source_name'])}, "
                f"{q(a['published_at_utc'])}, {q(a['published_at_cst'])}, "
                f"{q(a['time_precision'])}, {q(a['content_hash'])}, {q(flags)});"
            )
            n += 1

    # 接入批次留痕
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    lines += [
        "",
        "-- ingest_batches 留痕",
        f"INSERT INTO ingest_batches (trigger_key, origin, total, inserted, status, message) "
        f"VALUES ({q('init' + ts)}, 'crawler-export', {n}, {n}, 'succeeded', "
        f"{q(f'initial ETL from newsagg: {n} articles')});",
        "",
    ]

    out.write_text("\n".join(lines), encoding="utf-8")
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"✅ 导出完成：{out}")
    print(f"   provinces={len(provinces)} sources={len(sources)} articles={n}")
    print(f"   文件大小：{size_mb:.1f} MB")
    print(f"   上传到虚拟机后：docker compose exec -T mysql mysql -u<user> -p<pwd> "
          f"newsagg_platform < {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
