"""同意登记领域服务：撤回动作必须落下真实的撤回时间，用途复核据此判断历史时点。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.base import BaseModuleService


class ConsentRegistryService(BaseModuleService):
    MODULE = "consent_registry"
    ENTITY = "同意记录"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["记录编号", "数据主体", "处理目的", "同意范围", "同意时间", "撤回时间", "法律依据", "生效状态"]
    REQUIRED_FIELDS = ["记录编号", "数据主体", "处理目的"]
    STATUS_ORDER = ["已同意", "已撤回", "已过期"]
    ACTION_RULES = {"撤回同意": "已撤回", "标记过期": "已过期"}
    NEGATIVE_ACTIONS = []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry, message = super().run_action(entry_id, action)
        if entry is None:
            return entry, message
        if action == "撤回同意":
            # 撤回时间决定「访问发生时是否仍然有效」，必须写成可比较的绝对时间。
            entry["撤回时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry["生效状态"] = "已撤回"
        elif action == "标记过期":
            entry["生效状态"] = "已过期"
        return entry, message

    def create_effects(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """登记新同意后，把同主体、同目的的待核查事件标出来，供专员在审计页看到。"""
        from app.services.purpose_review import purpose_review_service

        summary = purpose_review_service.on_consent_registered(entry)
        return {"purpose_reviews": summary}
