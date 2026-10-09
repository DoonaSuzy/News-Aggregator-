"""常驻监督：维持固定数量的 worker 子进程，崩溃后自动重启。

用法::

    python -m newsagg supervisor

无 Windows 计划任务权限时可手动在终端运行本命令。
"""

from __future__ import annotations

import subprocess
import sys
import time

from newsagg.config import get_settings
from newsagg.logutil import get_logger

log = get_logger()


def _worker_cmd() -> list[str]:
    """构造 worker 子进程命令（当前解释器 + ``-m newsagg worker``）。"""
    return [sys.executable, "-m", "newsagg", "worker"]


class WorkerProcess:
    """单个 worker 子进程的薄封装。"""

    def __init__(self, index: int) -> None:
        self.index = index
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        cmd = _worker_cmd()
        log.info("启动 worker #%d: %s", self.index, " ".join(cmd))
        self.proc = subprocess.Popen(cmd)

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def supervise(worker_count: int | None = None) -> None:
    """维持 ``worker_count`` 个 worker，退出即重启，直到收到中断。"""
    settings = get_settings()
    n = worker_count or settings.worker_count
    procs = [WorkerProcess(i) for i in range(n)]
    for p in procs:
        p.start()

    log.info("supervisor 运行中，维持 %d 个 worker（Ctrl+C 退出）", n)
    try:
        while True:
            time.sleep(5)
            for p in procs:
                if not p.is_alive():
                    code = p.proc.returncode if p.proc else "?"
                    log.warning("worker #%d 退出(code=%s)，重启", p.index, code)
                    p.start()
    except KeyboardInterrupt:
        log.info("supervisor 收到中断，停止全部 worker")
    finally:
        for p in procs:
            p.stop()


__all__ = ["supervise", "WorkerProcess"]
