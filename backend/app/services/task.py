"""采集任务业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "task"
REQUIRED_FIELDS = ["任务编号", "任务名称", "关联源端"]
STATUS_ORDER = ["草稿", "待执行", "执行中", "已完成"]
ACTION_RULES = {"提交执行": "待执行", "暂停任务": "执行中", "恢复任务": "已完成"}
NEGATIVE_ACTIONS = []


def _schedule_state(row: dict[str, Any]) -> dict[str, Any]:
    """按关联抓取规则的实时状态推导可调度标记与阻断原因。

    只在读取时叠加在副本上，不回写任务记录本身，历史已执行结果保持不变。
    """
    item = dict(row)
    code = str(row.get("关联规则") or "").strip()
    item["可调度"] = "是"
    item["阻断原因"] = ""
    if not code:
        return item
    rule = next(
        (entry for entry in store.rows("website") if str(entry.get("规则编号", "")) == code),
        None,
    )
    if rule is None:
        item["可调度"] = "否"
        item["阻断原因"] = f"关联规则 {code} 不存在或已归档，任务调度被阻断"
    elif rule.get("status") != "已启用":
        item["可调度"] = "否"
        item["阻断原因"] = f"关联规则 {code} 当前状态为「{rule.get('status')}」，任务调度被阻断"
    return item


class TaskService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_schedule_state(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return _schedule_state(row)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"采集任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于采集任务可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"采集任务已{action}"
