"""调试用：以 DEBUG 日志跑一个来源，观察请求是否被丢弃。

用法: python scripts/debug_crawl.py <adapter>
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsagg.config import get_settings  # noqa: E402
from newsagg.crawl.settings import scrapy_settings  # noqa: E402
from newsagg.crawl.spider import SiteSpider  # noqa: E402
from newsagg.db import Database  # noqa: E402
from newsagg.repo import Repository  # noqa: E402
from newsagg.schedule import create_local_job  # noqa: E402
from newsagg.timewindow import Window  # noqa: E402
from newsagg.crawl.session import CrawlSession  # noqa: E402


def main(argv: list[str]) -> int:
    name = argv[1] if len(argv) > 1 else "hunan"
    job_id = create_local_job(name, days=7)
    print("job", job_id)

    settings = get_settings()
    db = Database()
    repo = Repository(db)
    conn = db.connect()
    try:
        row = repo.find_open_job(conn, job_id)
        meta = repo.get_job_source_meta(conn, job_id)
        claimed = repo.acquire_lease(conn, job_id, "debug", lease_seconds=settings.lease_seconds)
        conn.commit()
    finally:
        conn.close()
    job_row, lease = claimed
    window = Window(job_row.window_start_cst, job_row.window_end_cst, job_row.job_type)
    session = CrawlSession(
        job_id, source_id=int(meta["id"]), window=window, lease_token=lease.token,
        owner="debug", adapter_name=meta["adapter_name"], db=db, repo=repo,
        bloom=None,
    )
    column_url = meta["column_url"] or ""
    print("column_url =", column_url)

    from scrapy.crawler import CrawlerProcess

    process = CrawlerProcess(scrapy_settings(overrides={"LOG_LEVEL": "DEBUG"}))
    process.crawl(SiteSpider, session=session, column_url=column_url)
    process.start(stop_after_crawl=True)
    print("discovered", session.discovered, "saved", session.saved,
          "requests", session.requests, "stop", session.stop_reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
