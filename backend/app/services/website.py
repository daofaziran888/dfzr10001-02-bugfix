"""网页抓取规则业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import threading
from typing import Any

from app.store import store

MODULE = "website"
REQUIRED_FIELDS = ["规则编号", "目标站点", "列表选择器"]
STATUS_ORDER = ["草稿", "待校验", "已启用", "已停用"]
ACTION_RULES = {"提交校验": "待校验", "启用配置": "已启用", "停用配置": "已停用"}
NEGATIVE_ACTIONS = ["停用配置"]

# 状态只能按 草稿 → 待校验 → 已启用 → 已停用 单向推进；
# 已停用后只允许重新校验（提交校验回到待校验），不能直接恢复已启用。
TRANSITION_SOURCES = {
    "提交校验": {"草稿", "已停用"},
    "启用配置": {"待校验"},
    "停用配置": {"已启用"},
}


class WebsiteService:
    def __init__(self) -> None:
        # 串行化同一进程内的状态流转，保证并发重复启用只生效一次。
        self._action_lock = threading.Lock()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        site: str | None = None,
        selector: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("规则编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if site:
            rows = [row for row in rows if site in str(row.get("目标站点", ""))]
        if selector:
            rows = [row for row in rows if selector in str(row.get("列表选择器", ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

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
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于网页抓取规则可执行范围"
        # 校验与写状态必须在同一把锁里完成：并发重复启用时，后到请求读到的是
        # 已推进的状态，只会被拒绝，生效永远只有一次。
        with self._action_lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"抓取规则 {entry_id} 不存在或已归档"
            current = str(entry.get("status") or "")
            if current not in TRANSITION_SOURCES[action]:
                return None, self._reject_message(entry, action, current)
            target = ACTION_RULES[action]
            entry["status"] = target
            entry["pending"] = target in ("草稿", "待校验")
            entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"抓取规则已{action}"

    @staticmethod
    def _reject_message(entry: dict[str, Any], action: str, current: str) -> str:
        code = entry.get("规则编号") or entry.get("id")
        if action == "启用配置":
            if current == "已启用":
                return f"抓取规则 {code} 已是「已启用」，重复启用未生效"
            if current == "已停用":
                return f"抓取规则 {code} 已停用，重新启用只允许重新校验，不能恢复旧调度"
            return f"抓取规则 {code} 当前为「{current}」，需先提交校验，待校验通过后才能启用"
        if action == "停用配置":
            return f"抓取规则 {code} 当前为「{current}」，仅「已启用」的规则才能停用"
        return f"抓取规则 {code} 当前为「{current}」，仅「草稿」或「已停用」可提交校验"
