"""全部持久化逻辑：来源、批次、任务、租约、文章、审计。

本模块是唯一的 SQL 落点。调度（schedule）、采集会话（crawl.session）、
工作进程（worker）都通过 ``Repository`` 读写 MySQL，不直接写 SQL。

约定：
- 连接由调用方传入（``conn``），事务边界由调用方控制（``commit``/``rollback``）。
- 运行时刻字段写 UTC 墙钟（naive），``_cst`` 字段写北京时间墙钟，不随会话时区换算。
- 租约：``sources.lease_token`` + ``lease_owner`` + ``lease_until_utc``；
  写结果前核对 ``lease_token``，旧令牌不能覆盖他人结果。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from newsagg.db import Database

# 状态枚举（与 schema.sql 对齐）
_TERMINAL = ("succeeded", "partial")


@dataclass
class Lease:
    """一次成功认领得到的租约信息。"""

    token: str
    owner: str
    until_utc: datetime


@dataclass
class JobRow:
    """任务行快照（含来源租约字段）。"""

    id: int
    source_id: int
    job_type: str
    status: str
    window_start_cst: datetime | None
    window_end_cst: datetime | None
    retry_at_utc: datetime | None
    lease_token: str | None
    lease_owner: str | None
    lease_until_utc: datetime | None


@dataclass
class SourceRow:
    """来源行。"""

    id: int
    adapter_name: str
    province_code: str | None
    media_name: str
    column_url: str
    verification_status: str
    lease_token: str | None
    lease_owner: str | None
    lease_until_utc: datetime | None


@dataclass
class ArticleUpsert:
    """文章 upsert 结果。"""

    outcome: str  # "saved" | "updated" | "skipped"
    article_id: int | None


class Repository:
    """围绕 ``Database`` 的持久化门面。"""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def connect(self):
        return self.db.connect()

    # --- 来源 --------------------------------------------------------------

    def get_source(self, conn, *, source_id: int | None = None,
                   adapter_name: str | None = None) -> SourceRow | None:
        """按 id 或 adapter_name 取来源。"""
        if source_id is not None:
            sql, arg = "SELECT * FROM sources WHERE id = %s", source_id
        elif adapter_name is not None:
            sql, arg = "SELECT * FROM sources WHERE adapter_name = %s", adapter_name
        else:
            raise ValueError("需提供 source_id 或 adapter_name")
        with conn.cursor() as cur:
            cur.execute(sql, (arg,))
            row = cur.fetchone()
        return self._to_source(row)

    def list_enabled_slots(self, conn) -> list[dict[str, Any]]:
        """返回每省启用槽对应的启用来源。"""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT s.id, s.adapter_name, s.province_code, "
                "s.last_discovery_success_at_utc "
                "FROM source_slots sl JOIN sources s ON s.id = sl.source_id "
                "WHERE s.verification_status = 'enabled' "
                "ORDER BY s.province_code"
            )
            return cur.fetchall()

    def list_sources(self, conn) -> list[dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT adapter_name, media_name, province_code, "
                "verification_status, pause_reason, cooldown_until_utc "
                "FROM sources ORDER BY province_code, adapter_name"
            )
            return cur.fetchall()

    def enable_source(self, conn, adapter_name: str) -> bool:
        """启用来源（要求库里已有该来源的文章）。返回是否成功。"""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM articles a "
                "JOIN sources s ON s.id = a.source_id "
                "WHERE s.adapter_name = %s",
                (adapter_name,),
            )
            n = cur.fetchone()["n"]
            if not n:
                return False
            cur.execute(
                "UPDATE sources SET verification_status = 'enabled', "
                "pause_reason = NULL WHERE adapter_name = %s",
                (adapter_name,),
            )
        return True

    def resume_source(self, conn, adapter_name: str) -> None:
        """清除暂停与冷却，恢复启用。"""
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET verification_status = 'enabled', "
                "pause_reason = NULL, cooldown_until_utc = NULL "
                "WHERE adapter_name = %s",
                (adapter_name,),
            )

    def pause_source(self, conn, adapter_name: str, reason: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET verification_status = 'paused', "
                "pause_reason = %s WHERE adapter_name = %s",
                (reason, adapter_name),
            )

    def set_cooldown(self, conn, source_id: int, until_utc: datetime) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET cooldown_until_utc = %s WHERE id = %s",
                (until_utc, source_id),
            )

    def mark_discovery_success(self, conn, source_id: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET last_discovery_success_at_utc = CURRENT_TIMESTAMP "
                "WHERE id = %s",
                (source_id,),
            )


    # --- 批次 crawl_runs ---------------------------------------------------

    def insert_run(self, conn, trigger_key: str) -> int | None:
        """插入批次（幂等）。已存在返回 None。"""
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO crawl_runs (trigger_key, job_count) VALUES (%s, 0)",
                (trigger_key,),
            )
            if cur.rowcount == 0:
                return None
            return int(cur.lastrowid)

    def finish_run(self, conn, run_id: int, job_count: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE crawl_runs SET job_count = %s, "
                "finished_at_utc = CURRENT_TIMESTAMP WHERE id = %s",
                (job_count, run_id),
            )

    # --- 任务 crawl_jobs ---------------------------------------------------

    def create_job(self, conn, *, source_id: int, trigger_key: str, job_type: str,
                   window_start_cst: datetime, window_end_cst: datetime) -> int | None:
        """创建任务（幂等，靠唯一键）。已存在返回 None。"""
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO crawl_jobs "
                "(source_id, trigger_key, job_type, status, window_start_cst, window_end_cst) "
                "VALUES (%s, %s, %s, 'queued', %s, %s)",
                (source_id, trigger_key, job_type, window_start_cst, window_end_cst),
            )
            if cur.rowcount == 0:
                return None
            return int(cur.lastrowid)

    def find_open_job(self, conn, job_id: int) -> JobRow | None:
        """读取任务快照（含来源租约字段），供租约判定使用。"""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT j.id, j.source_id, j.job_type, j.status, "
                "j.window_start_cst, j.window_end_cst, j.retry_at_utc, "
                "s.lease_token, s.lease_owner, s.lease_until_utc "
                "FROM crawl_jobs j JOIN sources s ON s.id = j.source_id "
                "WHERE j.id = %s",
                (job_id,),
            )
            row = cur.fetchone()
        return self._to_job(row)

    def get_job_source_meta(self, conn, job_id: int) -> dict[str, Any] | None:
        """取任务的来源元信息（id / adapter_name / column_url）。"""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT s.id, s.adapter_name, s.column_url "
                "FROM crawl_jobs j JOIN sources s ON s.id = j.source_id "
                "WHERE j.id = %s",
                (job_id,),
            )
            return cur.fetchone()

    def today_done_count(self, conn, source_id: int, now_utc: datetime) -> int:
        """该来源今天（北京时间）已成功/部分完成的任务数。"""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM crawl_jobs "
                "WHERE source_id = %s AND status IN ('succeeded','partial') "
                "AND DATE(CONVERT_TZ(updated_at, '+00:00', '+08:00')) "
                "  = DATE(CONVERT_TZ(%s, '+00:00', '+08:00'))",
                (source_id, now_utc),
            )
            return int(cur.fetchone()["n"])


    # --- 租约 --------------------------------------------------------------

    def acquire_lease(self, conn, job_id: int, owner: str, *, lease_seconds: int
                      ) -> "tuple[JobRow, Lease] | None":
        """按租约认领一个任务。成功返回 (JobRow, Lease)。

        终态抛 ``JobTerminal``；他人持有有效租约抛 ``LeaseBusy``。
        调用方需在抛异常时 rollback。
        """
        from newsagg.errors import JobTerminal, LeaseBusy

        token = _new_token()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT j.status, j.job_type, j.window_start_cst, j.window_end_cst, "
                "s.lease_owner, s.lease_until_utc "
                "FROM crawl_jobs j JOIN sources s ON s.id = j.source_id "
                "WHERE j.id = %s FOR UPDATE",
                (job_id,),
            )
            job = cur.fetchone()
            if not job:
                raise KeyError(f"任务不存在: {job_id}")

            now = _utcnow()
            lease_active = (
                job["lease_until_utc"] is not None
                and job["lease_until_utc"] > now
                and bool(job["lease_owner"])
                and job["lease_owner"] != owner
            )
            if job["status"] in _TERMINAL:
                raise JobTerminal("任务已终态")
            if lease_active:
                raise LeaseBusy("他人持有有效租约")

            cur.execute(
                "UPDATE crawl_jobs SET status = 'running', "
                "attempt_count = attempt_count + 1 WHERE id = %s",
                (job_id,),
            )
            cur.execute(
                "UPDATE sources SET lease_token = %s, lease_owner = %s, "
                "lease_until_utc = DATE_ADD(%s, INTERVAL %s SECOND) "
                "WHERE id = (SELECT source_id FROM crawl_jobs WHERE id = %s)",
                (token, owner, now, lease_seconds, job_id),
            )
            cur.execute(
                "INSERT INTO job_attempts (job_id, attempt_no, owner) "
                "SELECT j.id, j.attempt_count, %s FROM crawl_jobs j WHERE j.id = %s "
                "ON DUPLICATE KEY UPDATE owner = %s",
                (owner, job_id, owner),
            )

        job_row = JobRow(
            id=job_id, source_id=0, job_type=job["job_type"], status="running",
            window_start_cst=job["window_start_cst"],
            window_end_cst=job["window_end_cst"], retry_at_utc=None,
            lease_token=token, lease_owner=owner, lease_until_utc=now,
        )
        return job_row, Lease(token=token, owner=owner, until_utc=now)

    def renew_lease(self, conn, *, source_id: int, token: str,
                    lease_seconds: int) -> bool:
        """续租。令牌不匹配返回 False（旧令牌不覆盖）。"""
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sources SET "
                "lease_until_utc = DATE_ADD(%s, INTERVAL %s SECOND) "
                "WHERE id = %s AND lease_token = %s",
                (_utcnow(), lease_seconds, source_id, token),
            )
            return cur.rowcount > 0


    # --- 候选 article_tasks ------------------------------------------------

    def upsert_discovered(self, conn, *, source_id: int, job_id: int,
                          url_hash: str, url: str) -> bool:
        """插入候选（幂等）。首次插入返回 True，已存在返回 False。"""
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO article_tasks "
                "(source_id, job_id, discovered_url_hash, url) VALUES (%s,%s,%s,%s)",
                (source_id, job_id, url_hash, url),
            )
            return cur.rowcount > 0

    def mark_task(self, conn, *, source_id: int, url_hash: str, status: str,
                  skip_reason: str | None = None,
                  failure_class: str | None = None) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE article_tasks SET status=%s, skip_reason=%s, failure_class=%s "
                "WHERE source_id=%s AND discovered_url_hash=%s",
                (status, skip_reason, failure_class, source_id, url_hash),
            )

    # --- 文章 articles -----------------------------------------------------

    def save_article(self, conn, *, source_id: int, url_hash: str, url: str,
                     title: str, body_text: str, source_name: str = "",
                     published_utc: datetime | None = None,
                     published_cst: datetime | None = None,
                     time_precision: str = "unknown",
                     content_hash: str = "",
                     quality_flags: list[str] | None = None) -> ArticleUpsert:
        """upsert 文章。身份 = (source_id, url_hash)。内容未变跳过。"""
        flags = json.dumps(quality_flags or [], ensure_ascii=False)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, content_hash FROM articles "
                "WHERE source_id = %s AND url_hash = %s",
                (source_id, url_hash),
            )
            existing = cur.fetchone()
            if existing:
                if existing["content_hash"] == content_hash:
                    return ArticleUpsert("skipped", existing["id"])
                cur.execute(
                    "UPDATE articles SET url=%s, title=%s, body_text=%s, "
                    "source_name=%s, published_at_utc=%s, published_at_cst=%s, "
                    "time_precision=%s, content_hash=%s, quality_flags=%s, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                    (url, title, body_text, source_name, published_utc,
                     published_cst, time_precision, content_hash, flags,
                     existing["id"]),
                )
                return ArticleUpsert("updated", existing["id"])

            cur.execute(
                "INSERT INTO articles "
                "(source_id, url_hash, url, title, body_text, source_name, "
                "published_at_utc, published_at_cst, time_precision, content_hash, "
                "quality_flags) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (source_id, url_hash, url, title, body_text, source_name,
                 published_utc, published_cst, time_precision, content_hash, flags),
            )
            return ArticleUpsert("saved", int(cur.lastrowid))

    # --- 任务收尾 ----------------------------------------------------------

    def finish_job(self, conn, *, job_id: int, status: str,
                   discovered: int = 0, saved: int = 0,
                   checkpoint_cst: datetime | None = None,
                   stop_reason: str | None = None,
                   advance_discovery: bool = False) -> None:
        """写终态 + 计数 + 检查点；可选推进发现成功时间与尝试结果。"""
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE crawl_jobs SET status=%s, discovered_count=%s, saved_count=%s, "
                "checkpoint_cst=%s, stop_reason=%s, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=%s",
                (status, discovered, saved, checkpoint_cst, stop_reason, job_id),
            )
            if advance_discovery:
                cur.execute(
                    "UPDATE sources SET last_discovery_success_at_utc=CURRENT_TIMESTAMP "
                    "WHERE id=(SELECT source_id FROM crawl_jobs WHERE id=%s)",
                    (job_id,),
                )
            cur.execute(
                "UPDATE job_attempts SET outcome=%s, finished_at_utc=CURRENT_TIMESTAMP "
                "WHERE job_id=%s AND attempt_no=("
                "SELECT attempt_count FROM crawl_jobs WHERE id=%s)",
                (status, job_id, job_id),
            )

    def set_retry(self, conn, *, job_id: int, retry_minutes: int,
                  stop_reason: str | None = None) -> None:
        """任务进入重试等待，到点后可被重新建批接管。"""
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE crawl_jobs SET status='retry_wait', "
                "retry_at_utc = DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s MINUTE), "
                "stop_reason=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (retry_minutes, stop_reason, job_id),
            )


    # --- 行映射 ------------------------------------------------------------

    @staticmethod
    def _to_source(row) -> SourceRow | None:
        if not row:
            return None
        return SourceRow(
            id=int(row["id"]),
            adapter_name=row["adapter_name"],
            province_code=row.get("province_code"),
            media_name=row.get("media_name", ""),
            column_url=row.get("column_url", ""),
            verification_status=row["verification_status"],
            lease_token=row.get("lease_token"),
            lease_owner=row.get("lease_owner"),
            lease_until_utc=row.get("lease_until_utc"),
        )

    @staticmethod
    def _to_job(row) -> JobRow | None:
        if not row:
            return None
        return JobRow(
            id=int(row["id"]),
            source_id=int(row["source_id"]),
            job_type=row["job_type"],
            status=row["status"],
            window_start_cst=row.get("window_start_cst"),
            window_end_cst=row.get("window_end_cst"),
            retry_at_utc=row.get("retry_at_utc"),
            lease_token=row.get("lease_token"),
            lease_owner=row.get("lease_owner"),
            lease_until_utc=row.get("lease_until_utc"),
        )


def _new_token() -> str:
    import uuid
    return uuid.uuid4().hex


def _utcnow():
    from newsagg.cleaning import utc_now_naive
    return utc_now_naive()


__all__ = [
    "Repository",
    "Lease",
    "JobRow",
    "SourceRow",
    "ArticleUpsert",
]

