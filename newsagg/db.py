"""MySQL 连接工厂、建表与种子来源数据。"""

from __future__ import annotations

from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from newsagg.config import get_settings
from newsagg.provinces import PROVINCES

# 34 个候选来源（adapter_name 唯一）。状态说明见文档 §2.4。
# 每个来源: adapter_name, province_code, media_name, column_url, verification_status
CANDIDATE_SOURCES: list[dict[str, str]] = [
    {"adapter_name": "beijing", "province_code": "11", "media_name": "千龙网", "column_url": "http://www.qianlong.com/news", "verification_status": "enabled"},
    {"adapter_name": "jinwan", "province_code": "12", "media_name": "今晚网", "column_url": "http://www.jinwan.gov.cn", "verification_status": "enabled"},
    {"adapter_name": "tianjin", "province_code": "12", "media_name": "北方网", "column_url": "http://news.enorth.com.cn", "verification_status": "candidate"},
    {"adapter_name": "hebei", "province_code": "13", "media_name": "河北新闻网", "column_url": "http://www.hebnews.cn", "verification_status": "enabled"},
    {"adapter_name": "shanxi", "province_code": "14", "media_name": "黄河新闻网", "column_url": "http://www.sxgov.cn", "verification_status": "enabled"},
    {"adapter_name": "neimenggu", "province_code": "15", "media_name": "正北方网", "column_url": "http://www.northnews.cn", "verification_status": "enabled"},
    {"adapter_name": "liaoning", "province_code": "21", "media_name": "东北新闻网", "column_url": "http://www.nen.com.cn", "verification_status": "enabled"},
    {"adapter_name": "jilin", "province_code": "22", "media_name": "中国吉林网", "column_url": "http://www.cnjiwang.com", "verification_status": "enabled"},
    {"adapter_name": "heilongjiang", "province_code": "23", "media_name": "黑龙江新闻网", "column_url": "http://www.hljnews.cn", "verification_status": "enabled"},
    {"adapter_name": "laodong", "province_code": "31", "media_name": "劳动报", "column_url": "http://www.51ldb.com/shsldb", "verification_status": "enabled"},
    {"adapter_name": "jiangsu", "province_code": "32", "media_name": "中国江苏网", "column_url": "http://www.jschina.com.cn", "verification_status": "enabled"},
    {"adapter_name": "zhejiang", "province_code": "33", "media_name": "浙江在线", "column_url": "http://www.zjol.com.cn", "verification_status": "enabled"},
    {"adapter_name": "anhui", "province_code": "34", "media_name": "安徽新闻网", "column_url": "http://www.anhuinews.com", "verification_status": "enabled"},
    {"adapter_name": "fujian", "province_code": "35", "media_name": "东南网", "column_url": "http://www.fjsen.com", "verification_status": "enabled"},
    {"adapter_name": "jiangxi", "province_code": "36", "media_name": "大江网", "column_url": "http://www.jxnews.com.cn", "verification_status": "enabled"},
    {"adapter_name": "shandong", "province_code": "37", "media_name": "大众网", "column_url": "http://www.dzwww.com", "verification_status": "enabled"},
    {"adapter_name": "henan", "province_code": "41", "media_name": "大河网", "column_url": "http://www.dahe.cn", "verification_status": "enabled"},
    {"adapter_name": "changjiang", "province_code": "42", "media_name": "长江网", "column_url": "http://www.cjn.cn", "verification_status": "enabled"},
    {"adapter_name": "hubei", "province_code": "42", "media_name": "荆楚网", "column_url": "http://www.cnhubei.com", "verification_status": "candidate"},
    {"adapter_name": "hunan", "province_code": "43", "media_name": "红网", "column_url": "http://www.rednet.cn", "verification_status": "enabled"},
    {"adapter_name": "guangdong", "province_code": "44", "media_name": "南方网", "column_url": "http://www.southcn.com", "verification_status": "enabled"},
    {"adapter_name": "gxtv", "province_code": "45", "media_name": "广西网络广播电视台", "column_url": "http://www.gxtv.cn", "verification_status": "enabled"},
    {"adapter_name": "hainan", "province_code": "46", "media_name": "南海网", "column_url": "http://www.hinews.cn", "verification_status": "enabled"},
    {"adapter_name": "chongqing", "province_code": "50", "media_name": "华龙网", "column_url": "http://www.cqnews.net", "verification_status": "enabled"},
    {"adapter_name": "sichuan", "province_code": "51", "media_name": "四川新闻网", "column_url": "http://www.newssc.org", "verification_status": "enabled"},
    {"adapter_name": "guizhou", "province_code": "52", "media_name": "当代先锋网", "column_url": "http://www.ddxfw.cn", "verification_status": "enabled"},
    {"adapter_name": "yunnan", "province_code": "53", "media_name": "云南网", "column_url": "http://www.yunnan.cn", "verification_status": "enabled"},
    {"adapter_name": "xizang", "province_code": "54", "media_name": "中国西藏新闻网", "column_url": "http://www.chinatibetnews.com", "verification_status": "enabled"},
    {"adapter_name": "shaanxi", "province_code": "61", "media_name": "华商网", "column_url": "http://www.hsw.cn", "verification_status": "enabled"},
    {"adapter_name": "gansudaily", "province_code": "62", "media_name": "每日甘肃网", "column_url": "http://www.gansudaily.com.cn", "verification_status": "enabled"},
    {"adapter_name": "gansu", "province_code": "62", "media_name": "中国甘肃网", "column_url": "http://www.gscn.com.cn", "verification_status": "candidate"},
    {"adapter_name": "qinghai", "province_code": "63", "media_name": "青海新闻网", "column_url": "http://www.qhnews.com", "verification_status": "enabled"},
    {"adapter_name": "ningxia", "province_code": "64", "media_name": "银川新闻网", "column_url": "http://www.ycen.com.cn", "verification_status": "enabled"},
    {"adapter_name": "xinjiang", "province_code": "65", "media_name": "新疆网", "column_url": "http://www.xinjiangnet.com.cn", "verification_status": "enabled"},
]


class Database:
    """MySQL 连接工厂（utf8mb4、DictCursor、UTC 会话时区）。"""

    def __init__(self) -> None:
        self._settings = get_settings()

    def connect(self) -> pymysql.connections.Connection:
        s = self._settings
        conn = pymysql.connect(
            host=s.mysql_host,
            port=s.mysql_port,
            user=s.mysql_user,
            password=s.mysql_password,
            database=s.mysql_database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )
        cur = conn.cursor()
        cur.execute("SET time_zone = '+00:00'")
        cur.close()
        return conn

    def ping(self) -> dict[str, Any]:
        """返回版本与字符集信息（连通性自检）。"""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION() AS version")
                version = cur.fetchone()["version"]
                cur.execute(
                    "SELECT @@character_set_server AS cs, @@collation_server AS coll"
                )
                row = cur.fetchone()
            return {
                "version": version,
                "charset": row["cs"],
                "collation": row["coll"],
            }
        finally:
            conn.close()


def _schema_sql() -> str:
    root = get_settings().root
    return (root / "sql" / "schema.sql").read_text(encoding="utf-8")


def _split_statements(sql: str) -> list[str]:
    """按分号切分 SQL（简单实现，schema.sql 不含存储过程）。"""
    statements: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        buf.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buf))
            buf = []
    if buf:
        statements.append("\n".join(buf))
    return statements


def init_database() -> dict[str, int]:
    """执行建表脚本，写入省份与候选来源种子。

    已存在的 ``adapter_name`` 不会被覆盖。
    """
    db = Database()
    conn = db.connect()
    provinces_added = 0
    sources_added = 0
    try:
        with conn.cursor() as cur:
            for statement in _split_statements(_schema_sql()):
                if statement.strip():
                    cur.execute(statement)

            for code, name in PROVINCES:
                cur.execute(
                    "INSERT IGNORE INTO provinces (code, name) VALUES (%s, %s)",
                    (code, name),
                )
                if cur.rowcount > 0:
                    provinces_added += 1

            for src in CANDIDATE_SOURCES:
                cur.execute(
                    "INSERT IGNORE INTO sources "
                    "(adapter_name, province_code, media_name, column_url, verification_status) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        src["adapter_name"],
                        src["province_code"],
                        src["media_name"],
                        src["column_url"],
                        src["verification_status"],
                    ),
                )
                if cur.rowcount > 0:
                    sources_added += 1

            # 为每个有 enabled 来源的省建立启用槽（每省一个）
            cur.execute(
                "INSERT IGNORE INTO source_slots (province_code, source_id) "
                "SELECT s.province_code, MIN(s.id) FROM sources s "
                "WHERE s.verification_status = 'enabled' AND s.province_code IS NOT NULL "
                "GROUP BY s.province_code"
            )
        conn.commit()
        return {"provinces_added": provinces_added, "sources_added": sources_added}
    finally:
        conn.close()


__all__ = ["Database", "CANDIDATE_SOURCES", "init_database"]

