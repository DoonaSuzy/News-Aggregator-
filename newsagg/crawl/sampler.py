"""失败采样与空页采样。"""

from __future__ import annotations

import os
from datetime import datetime


class Sampler:
    """把失败/空页样本写到 logs/ 目录（每轮上限 FAIL_SAMPLE_PER_RUN）。"""

    def __init__(self, log_dir: str, *, per_run: int = 200) -> None:
        self.log_dir = log_dir
        self.per_run = per_run
        self._written = 0
        os.makedirs(os.path.join(log_dir, "samples"), exist_ok=True)

    def save_failure(self, url: str, status: int | None, html: str | None, *, label: str) -> str | None:
        if self._written >= self.per_run:
            return None
        self._written += 1
        name = f"{label}_{self._written}.html"
        path = os.path.join(self.log_dir, "samples", name)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"<!-- url={url} status={status} time={datetime.utcnow().isoformat()} -->\n")
                fh.write(html or "")
        except OSError:
            return None
        return path


__all__ = ["Sampler"]
