"""投递分类：判定一条消息应 run / wait / ack。

- 终态（succeeded/partial/failed 且未到重试时间）→ ack
- 租约有效但属他人 → wait
- 否则 → run
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from newsagg.errors import LeaseBusy, NotDue


class Decision(str, Enum):
    RUN = "run"
    WAIT = "wait"
    ACK = "ack"


@dataclass
class JobSnapshot:
    """判定所需的任务/来源快照。"""

    status: str
    lease_token: str | None = None
    lease_owner: str | None = None
    lease_until_utc: datetime | None = None
    retry_at_utc: datetime | None = None


_TERMINAL = {"succeeded", "partial"}


def classify_delivery(snapshot: JobSnapshot, *, now_utc: datetime, owner: str) -> Decision:
    """根据快照给出投递决策。

    :param owner: 当前 worker 身份（用于租约归属比较）。
    """
    # 终态：直接 ack
    if snapshot.status in _TERMINAL:
        return Decision.ACK
    if snapshot.status == "failed" and (snapshot.retry_at_utc is None or snapshot.retry_at_utc <= now_utc):
        return Decision.ACK

    # 重试等待未到：ack（消息稍后会被重新投递）
    if snapshot.status == "retry_wait":
        if snapshot.retry_at_utc and snapshot.retry_at_utc > now_utc:
            raise NotDue("重试时间未到")
        return Decision.ACK

    # 租约有效但属他人：wait
    if (
        snapshot.lease_token
        and snapshot.lease_until_utc
        and snapshot.lease_until_utc > now_utc
        and snapshot.lease_owner
        and snapshot.lease_owner != owner
    ):
        raise LeaseBusy("他人持有有效租约")

    return Decision.RUN


__all__ = ["Decision", "JobSnapshot", "classify_delivery"]
