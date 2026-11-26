"""访问审计领域服务：审计记录本身仍走状态流转，用途复核由独立服务承担。"""
from __future__ import annotations

from app.services.base import BaseModuleService


class AccessAuditService(BaseModuleService):
    MODULE = "access_audit"
    ENTITY = "审计记录"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["记录编号", "访问主体", "目标资源", "访问操作", "访问时间", "请求IP", "访问结果", "敏感等级"]
    REQUIRED_FIELDS = ["记录编号", "访问主体", "目标资源"]
    STATUS_ORDER = ["已记录", "需复核", "已异常"]
    ACTION_RULES = {"标记复核": "需复核", "标记异常": "已异常"}
    NEGATIVE_ACTIONS = []
    # 用途复核需要把同意登记的数据主体与处理目的对到审计事件上，这两个字段不进入列表列。
    CONTEXT_FIELDS = ["数据主体", "处理目的"]
