"""用途复核领域服务：按访问发生时点核对同意登记，出具历史用途单。

三条不可动摇的规则：
1. 同意是否有效按「访问发生时点」判断，访问后才撤回不能倒推为无授权；
2. 签署只能引用访问时覆盖本事件处理目的的凭据，其他用途的同意不可借用；
3. 已签署的结论冻结，补证/补录只能归入未落定的复核，或另立待核查事项。
"""
from __future__ import annotations

import copy
import threading
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "purpose_review"
ENTITY = "用途复核"
OPEN_STATUSES = ("待签署", "补证中")
STATUS_SIGNED = "已签署"
CONCLUSION_VALID = "访问时存在有效同意"
CONCLUSION_NONE = "访问时未登记有效同意"
CONCLUSION_LATE = "访问后补登同意，不追溯"

_LOCK = threading.Lock()


# ——————————————— 时间与文本工具 ———————————————


def parse_ts(value: Any) -> datetime | None:
    """把种子数据和手工录入里的多种时间写法统一成可比较的 datetime。"""
    text = str(value or "").strip()
    if not text or text in ("未撤回", "—", "-", "N/A"):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _fmt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _same(left: Any, right: Any) -> bool:
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def _minutes(later: datetime, earlier: datetime) -> int:
    return int((later - earlier).total_seconds() // 60)


# ——————————————— 同意核对 ———————————————


def consent_check(consent: dict[str, Any], access_at: datetime, purpose: Any) -> dict[str, Any]:
    """判断一条同意记录在访问时点是否覆盖本次处理目的。

    返回的「可用」决定它能否被签署引用；「判定」用于详情页展示核对结果。
    """
    base = {
        "id": consent.get("id"),
        "记录编号": consent.get("记录编号"),
        "数据主体": consent.get("数据主体"),
        "处理目的": consent.get("处理目的"),
        "同意时间": consent.get("同意时间"),
        "撤回时间": consent.get("撤回时间"),
        "生效状态": consent.get("生效状态"),
    }
    consent_purpose = consent.get("处理目的")
    if not _same(consent_purpose, purpose):
        return {
            **base,
            "可用": False,
            "判定": "处理目的不匹配",
            "说明": f"该凭据覆盖「{consent_purpose}」，不覆盖本次事件的「{purpose}」，不能用于签署。",
        }

    signed_at = parse_ts(consent.get("同意时间"))
    withdrawn_at = parse_ts(consent.get("撤回时间"))
    status = str(consent.get("status") or "")

    if signed_at is None:
        return {
            **base,
            "可用": False,
            "判定": "同意时间不可识别",
            "说明": "同意时间缺失或无法解析，无法证明访问时已经授权。",
        }

    if withdrawn_at is not None:
        if withdrawn_at <= access_at:
            return {
                **base,
                "可用": False,
                "判定": "访问前已撤回",
                "说明": f"撤回时间 {_fmt(withdrawn_at)} 不晚于访问时间 {_fmt(access_at)}，访问时授权已失效。",
            }
        if signed_at > access_at:
            return {
                **base,
                "可用": False,
                "判定": "访问后才签署",
                "说明": f"同意签署于 {_fmt(signed_at)}，晚于访问时间 {_fmt(access_at)}，不追溯为访问时授权。",
            }
        return {
            **base,
            "可用": True,
            "判定": "访问时有效",
            "说明": (
                f"同意签署于 {_fmt(signed_at)}，撤回于 {_fmt(withdrawn_at)}；"
                f"访问发生在 {_fmt(access_at)}，早于撤回 {_minutes(withdrawn_at, access_at)} 分钟，访问时授权成立。"
            ),
        }

    if status == "已撤回":
        return {
            **base,
            "可用": False,
            "判定": "已撤回但无撤回时间",
            "说明": "记录已标记撤回却没有撤回时间，无法证明访问时授权仍然有效。",
        }
    if status == "已过期":
        return {
            **base,
            "可用": False,
            "判定": "已过期",
            "说明": "该同意已失效，访问时不再构成有效授权。",
        }
    if signed_at > access_at:
        return {
            **base,
            "可用": False,
            "判定": "访问后才签署",
            "说明": f"同意签署于 {_fmt(signed_at)}，晚于访问时间 {_fmt(access_at)}，不追溯为访问时授权。",
        }
    return {
        **base,
        "可用": True,
        "判定": "访问时有效",
        "说明": f"同意签署于 {_fmt(signed_at)}，访问时点尚未撤回也未过期。",
    }


def _checks_for_audit(audit: dict[str, Any]) -> list[dict[str, Any]]:
    access_at = parse_ts(audit.get("访问时间"))
    if access_at is None:
        return []
    subject = audit.get("数据主体")
    purpose = audit.get("处理目的")
    consents = [
        row for row in store.rows("consent_registry")
        if _same(row.get("数据主体"), subject)
    ]
    return [consent_check(row, access_at, purpose) for row in consents]


def _usable_ids(audit: dict[str, Any]) -> list[int]:
    return [int(item["id"]) for item in _checks_for_audit(audit) if item["可用"]]


def _build_purpose_doc(
    audit: dict[str, Any], *, operator: str, version: int,
) -> dict[str, Any]:
    """生成历史用途单：判定、依据与时间线全部落在访问时点上。"""
    checks = _checks_for_audit(audit)
    usable = [item for item in checks if item["可用"]]
    late = [item for item in checks if item["判定"] == "访问后才签署"]
    access_at = parse_ts(audit.get("访问时间"))

    if usable:
        cited = max(usable, key=lambda item: parse_ts(item["同意时间"]) or datetime.min)
        conclusion = CONCLUSION_VALID
        evidence = cited
        summary = (
            f"经核对同意登记，{cited['记录编号']} 覆盖本次处理目的「{audit.get('处理目的')}」，"
            f"且在访问时点有效。{cited['说明']}"
        )
    elif late:
        evidence = max(late, key=lambda item: parse_ts(item["同意时间"]) or datetime.min)
        conclusion = CONCLUSION_LATE
        summary = f"{evidence['记录编号']} 的同意晚于访问发生，属于事后补登，不作为访问当时授权。"
    else:
        evidence = None
        conclusion = CONCLUSION_NONE
        summary = (
            f"该数据主体在「{audit.get('处理目的')}」下没有在访问时点有效的同意记录，"
            "访问发生时未取得授权。"
        )

    timeline: list[dict[str, str]] = []
    if evidence is not None:
        timeline.append({"节点": "同意签署", "时间": str(evidence["同意时间"]), "凭据": str(evidence["记录编号"])})
    timeline.append({
        "节点": "访问发生",
        "时间": str(audit.get("访问时间")),
        "凭据": str(audit.get("记录编号")),
    })
    if evidence is not None and evidence.get("撤回时间"):
        timeline.append({"节点": "同意撤回", "时间": str(evidence["撤回时间"]), "凭据": str(evidence["记录编号"])})

    doc = {
        "单据编号": None,
        "审计记录ID": audit.get("id"),
        "记录编号": audit.get("记录编号"),
        "访问事件": {
            "访问主体": audit.get("访问主体"),
            "目标资源": audit.get("目标资源"),
            "访问操作": audit.get("访问操作"),
            "访问时间": audit.get("访问时间"),
            "访问结果": audit.get("访问结果"),
        },
        "数据主体": audit.get("数据主体"),
        "处理目的": audit.get("处理目的"),
        "判定": conclusion,
        "引用建议": evidence["记录编号"] if evidence is not None else "—",
        "依据": summary,
        "时间线": timeline,
        "出具时间": _now(),
        "出具人": operator,
        "版本": version,
    }
    if access_at is None:
        doc["依据"] = "访问时间缺失或无法解析，不能按访问时点核对同意登记。"
        doc["判定"] = "无法核对"
    return {
        "conclusion": doc["判定"],
        "summary": summary,
        "doc": doc,
        "checks": checks,
        "usable_ids": [int(item["id"]) for item in usable],
        "paper_numbers": [str(item["记录编号"]) for item in usable],
    }


def _next_id() -> int:
    return max((int(row.get("id", 0)) for row in store.rows(MODULE)), default=0) + 1


def _number(entry_id: int) -> str:
    return f"PURP-{entry_id:04d}"


# ——————————————— 服务实现 ———————————————


class PurposeReviewService:
    MODULE = MODULE
    ENTITY = ENTITY

    # —— 查询 ——

    def reviews_for_event(self, audit_id: int) -> list[dict[str, Any]]:
        return sorted(
            (row for row in store.rows(MODULE) if int(row.get("审计记录ID", 0)) == audit_id),
            key=lambda row: int(row.get("id", 0)),
        )

    def open_review(self, audit_id: int) -> dict[str, Any] | None:
        for row in reversed(self.reviews_for_event(audit_id)):
            if row.get("status") in OPEN_STATUSES:
                return row
        return None

    def event_packet(self, audit_id: int) -> dict[str, Any] | None:
        """详情页数据：审计事件、同意核对、已有复核。"""
        audit = store.find("access_audit", audit_id)
        if audit is None:
            return None
        checks = _checks_for_audit(audit)
        checks_by_id = {int(item["id"]): item for item in checks if item["id"] is not None}
        consents = []
        for row in store.rows("consent_registry"):
            if not _same(row.get("数据主体"), audit.get("数据主体")):
                continue
            check = checks_by_id.get(int(row.get("id", 0)))
            consents.append({
                **row,
                "核对": check or {
                    "可用": False,
                    "判定": "无法核对",
                    "说明": "访问时间缺失或无法解析。",
                },
            })
        return {
            "audit": audit,
            "consents": consents,
            "reviews": self.reviews_for_event(audit_id),
            "open_review": self.open_review(audit_id),
            "candidates": [item for item in checks if item["可用"]],
        }

    # —— 提交复核并出具历史用途单 ——

    def submit(
        self, audit_id: int, *, operator: str | None = None, reason: str | None = None,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
        with _LOCK:
            audit = store.find("access_audit", audit_id)
            if audit is None:
                return None, f"审计记录 {audit_id} 不存在或已归档", None
            if parse_ts(audit.get("访问时间")) is None:
                return None, "审计记录的访问时间无法解析，不能按访问时点核对同意登记", None

            operator = (operator or "").strip() or "合规专员"
            existing_open = self.open_review(audit_id)
            if existing_open is not None:
                return (
                    existing_open,
                    "该事件已有待核查的用途复核，本次提交归入当前审查，未另立记录",
                    {
                        "处置": "归入当前审查",
                        "review_id": existing_open["id"],
                        "复核编号": existing_open["复核编号"],
                    },
                )

            signed = [row for row in self.reviews_for_event(audit_id) if row.get("status") == STATUS_SIGNED]
            row = self._create_review(
                audit, operator=operator, source="专员提交", linked_id=None, reason=reason,
            )
            message = "已核对同意登记并出具历史用途单"
            disposition = "新建复核"
            if signed:
                message = "该事件已有签署结论，本次另立复核，原签署结论保持不变"
                disposition = "另立复核（原签署结论不变）"
            return row, message, {
                "处置": disposition,
                "review_id": row["id"],
                "复核编号": row["复核编号"],
                "用途单": row["用途单"],
                "候选同意": row["候选同意"],
            }

    def _create_review(
        self,
        audit: dict[str, Any],
        *,
        operator: str,
        source: str,
        linked_id: int | None,
        reason: str | None = None,
        evidence_consent: dict[str, Any] | None = None,
        conflict: str = "",
    ) -> dict[str, Any]:
        row_id = _next_id()
        build = _build_purpose_doc(audit, operator=operator, version=1)
        build["doc"]["单据编号"] = _number(row_id)
        row: dict[str, Any] = {
            "id": row_id,
            "status": "待签署",
            "pending": True,
            "abnormal": False,
            "复核编号": _number(row_id),
            "审计记录ID": audit.get("id"),
            "记录编号": audit.get("记录编号"),
            "访问主体": audit.get("访问主体"),
            "目标资源": audit.get("目标资源"),
            "访问操作": audit.get("访问操作"),
            "数据主体": audit.get("数据主体"),
            "处理目的": audit.get("处理目的"),
            "访问时间": audit.get("访问时间"),
            "审查结论": build["conclusion"],
            "结论说明": build["summary"],
            "候选同意": build["paper_numbers"],
            "引用同意": "",
            "用途单": build["doc"],
            "来源": source,
            "关联审查ID": linked_id,
            "发起人": operator,
            "创建时间": _now(),
            "签署人": "",
            "签署时间": "",
            "签署意见": "",
            "签署存档": None,
            "补证记录": [],
            "证据同意": [evidence_consent["记录编号"]] if evidence_consent else [],
            "冲突提示": conflict,
        }
        store.rows(MODULE).append(row)
        return row

    # —— 签署 ——

    def sign(
        self,
        review_id: int,
        *,
        signer: str,
        consent_id: int | None = None,
        conclusion: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        with _LOCK:
            row = store.find(MODULE, review_id)
            if row is None:
                return None, f"用途复核 {review_id} 不存在或已归档"
            if row.get("status") == STATUS_SIGNED:
                return None, "该复核已签署，历史结论不可改动；如需补充材料请发起补证复核"
            signer = (signer or "").strip()
            if not signer:
                return None, "签署人不能为空"

            audit = store.find("access_audit", int(row.get("审计记录ID", 0)))
            if audit is None:
                return None, "关联的审计记录不存在，无法核对同意凭据"
            checks = _checks_for_audit(audit)
            usable = [item for item in checks if item["可用"]]

            if consent_id is not None:
                consent = store.find("consent_registry", int(consent_id))
                if consent is None:
                    return None, f"同意记录 {consent_id} 不存在，不能引用"
                access_at = parse_ts(audit.get("访问时间"))
                check = consent_check(consent, access_at, audit.get("处理目的"))
                if not check["可用"]:
                    return None, f"不能引用 {consent.get('记录编号')} 签署：{check['说明']}"
                cited = check
            else:
                if usable:
                    numbers = "、".join(str(item["记录编号"]) for item in usable)
                    return None, (
                        f"访问发生时存在覆盖「{audit.get('处理目的')}」的有效同意（{numbers}），"
                        "签署必须引用对应凭据，不能以其他用途的同意代替"
                    )
                cited = None

            build = _build_purpose_doc(audit, operator=signer, version=int(
                row.get("用途单", {}).get("版本", 1)) + 1)
            build["doc"]["单据编号"] = row.get("复核编号")
            row["用途单"] = build["doc"]
            row["审查结论"] = build["conclusion"] if cited is not None else (
                CONCLUSION_LATE if build["conclusion"] == CONCLUSION_LATE else CONCLUSION_NONE
            )
            row["结论说明"] = build["summary"]
            row["引用同意"] = str(cited["记录编号"]) if cited is not None else ""
            row["签署人"] = signer
            row["签署时间"] = _now()
            row["签署意见"] = (conclusion or "").strip()
            row["签署存档"] = {
                "审查结论": row["审查结论"],
                "引用同意": row["引用同意"],
                "签署人": signer,
                "签署时间": row["签署时间"],
                "用途单": copy.deepcopy(build["doc"]),
            }
            row["status"] = STATUS_SIGNED
            row["pending"] = False
            return row, (
                f"用途复核已签署，引用凭据 {row['引用同意']}"
                if row["引用同意"] else "用途复核已签署，确认访问时无有效同意"
            )

    # —— 补证复核 ——

    def supplement(
        self,
        review_id: int,
        *,
        operator: str | None = None,
        reason: str,
        evidence: str | None = None,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
        with _LOCK:
            row = store.find(MODULE, review_id)
            if row is None:
                return None, f"用途复核 {review_id} 不存在或已归档", None
            reason = (reason or "").strip()
            if not reason:
                return None, "补证复核必须填写补证原因", None
            operator = (operator or "").strip() or "合规专员"
            audit = store.find("access_audit", int(row.get("审计记录ID", 0)))
            if audit is None:
                return None, "关联的审计记录不存在，无法补证", None

            if row.get("status") == STATUS_SIGNED:
                opened = self.open_review(int(audit["id"]))
                if opened is not None and opened is not row:
                    self._fold_supplement(opened, operator, reason, evidence)
                    return opened, (
                        "原复核已签署，补证材料归入该事件正在进行的待核查事项，原签署结论保持不变"
                    ), {"处置": "归入当前审查", "review_id": opened["id"], "复核编号": opened["复核编号"]}
                new_row = self._create_review(
                    audit,
                    operator=operator,
                    source="补证发起",
                    linked_id=int(row["id"]),
                    reason=reason,
                    conflict=(
                        f"针对已签署复核 {row.get('复核编号')} 的补证，"
                        "另立待核查事项；历史签署结论保持签署时状态。"
                    ),
                )
                new_row["补证记录"].append({
                    "类型": "发起补证",
                    "操作人": operator,
                    "原因": reason,
                    "材料": (evidence or "").strip(),
                    "时间": _now(),
                    "关联签署复核": row.get("复核编号"),
                })
                return new_row, (
                    "原复核已签署，补证材料形成该事件上另一次待核查事项，原签署结论保持不变"
                ), {
                    "处置": "形成该事件上另一次待核查事项",
                    "review_id": new_row["id"],
                    "复核编号": new_row["复核编号"],
                    "原复核编号": row.get("复核编号"),
                    "用途单": new_row["用途单"],
                }

            self._fold_supplement(row, operator, reason, evidence)
            return row, "补证材料已归入当前审查", {
                "处置": "归入当前审查",
                "review_id": row["id"],
                "复核编号": row["复核编号"],
                "用途单": row["用途单"],
            }

    def _fold_supplement(
        self, row: dict[str, Any], operator: str, reason: str, evidence: str | None,
    ) -> None:
        audit = store.find("access_audit", int(row.get("审计记录ID", 0)))
        if audit is None:
            return
        previous = str(row.get("审查结论") or "")
        build = _build_purpose_doc(
            audit, operator=operator, version=int(row.get("用途单", {}).get("版本", 1)) + 1)
        build["doc"]["单据编号"] = row.get("复核编号")
        row["用途单"] = build["doc"]
        row["审查结论"] = build["conclusion"]
        row["结论说明"] = build["summary"]
        row["候选同意"] = build["paper_numbers"]
        row["补证记录"].append({
            "类型": "补充材料",
            "操作人": operator,
            "原因": reason,
            "材料": (evidence or "").strip(),
            "时间": _now(),
        })
        row["status"] = "补证中"
        if previous and previous != build["conclusion"]:
            row["冲突提示"] = (
                f"补证后核查结论由「{previous}」变为「{build['conclusion']}」；"
                "原复核尚未签署，按补证后的结论继续核查。"
            )
        elif not row.get("冲突提示"):
            row["冲突提示"] = ""

    # —— 同意补录归并 ——

    def on_consent_registered(self, consent: dict[str, Any]) -> dict[str, Any]:
        """登记新同意后，把补录凭据归入该事件正在进行或已经签署的复核。"""
        with _LOCK:
            subject = consent.get("数据主体")
            purpose = consent.get("处理目的")
            events = [
                audit for audit in store.rows("access_audit")
                if _same(audit.get("数据主体"), subject) and _same(audit.get("处理目的"), purpose)
            ]
            if not events:
                return {
                    "处置": "无需归并",
                    "说明": "未找到与该同意记录对应的访问事件，未影响任何用途复核。",
                    "events": [],
                }

            results: list[dict[str, Any]] = []
            for audit in events:
                reviews = self.reviews_for_event(int(audit.get("id", 0)))
                if not reviews:
                    results.append({
                        "audit_id": audit.get("id"),
                        "记录编号": audit.get("记录编号"),
                        "处置": "未涉及复核",
                        "说明": "该事件尚未提交用途复核。",
                    })
                    continue
                open_rows = [row for row in reviews if row.get("status") in OPEN_STATUSES]
                if open_rows:
                    target = max(open_rows, key=lambda row: int(row.get("id", 0)))
                    previous = str(target.get("审查结论") or "")
                    number = str(consent.get("记录编号"))
                    if number not in target.get("证据同意", []):
                        target.setdefault("证据同意", []).append(number)
                    target.setdefault("补证记录", []).append({
                        "类型": "补录凭据",
                        "操作人": "同意登记",
                        "原因": f"补录同意记录 {number}",
                        "材料": f"{consent.get('同意时间')} 签署 / {consent.get('撤回时间')} 撤回",
                        "时间": _now(),
                    })
                    build = _build_purpose_doc(
                        audit,
                        operator=str(target.get("发起人") or "合规专员"),
                        version=int(target.get("用途单", {}).get("版本", 1)) + 1,
                    )
                    build["doc"]["单据编号"] = target.get("复核编号")
                    target["用途单"] = build["doc"]
                    target["审查结论"] = build["conclusion"]
                    target["结论说明"] = build["summary"]
                    target["候选同意"] = build["paper_numbers"]
                    target["status"] = "补证中"
                    changed = bool(previous) and previous != build["conclusion"]
                    if changed:
                        target["冲突提示"] = (
                            f"补录凭据 {number} 使核查结论由「{previous}」变为「{build['conclusion']}」；"
                            "原复核尚未落定，已归入当前审查并按补录后的结论继续核查。"
                        )
                    results.append({
                        "audit_id": audit.get("id"),
                        "记录编号": audit.get("记录编号"),
                        "review_id": target.get("id"),
                        "复核编号": target.get("复核编号"),
                        "处置": "归入当前审查",
                        "结论变化": f"{previous} → {build['conclusion']}" if changed else "结论未变",
                        "冲突提示": target.get("冲突提示", ""),
                    })
                    continue

                signed = max(
                    (row for row in reviews if row.get("status") == STATUS_SIGNED),
                    key=lambda row: int(row.get("id", 0)),
                )
                signed_conclusion = str(signed.get("审查结论") or "")
                new_row = self._create_review(
                    audit,
                    operator="同意登记员",
                    source="补录触发",
                    linked_id=int(signed.get("id", 0)),
                    evidence_consent=consent,
                    conflict="",
                )
                new_row["补证记录"].append({
                    "类型": "补录凭据",
                    "操作人": "同意登记",
                    "原因": f"补录同意记录 {consent.get('记录编号')}",
                    "材料": f"{consent.get('同意时间')} 签署 / {consent.get('撤回时间')} 撤回",
                    "时间": _now(),
                    "关联签署复核": signed.get("复核编号"),
                })
                contradicts = (
                    signed_conclusion == CONCLUSION_NONE and new_row["审查结论"] == CONCLUSION_VALID
                ) or (
                    signed_conclusion == CONCLUSION_VALID and new_row["审查结论"] != CONCLUSION_VALID
                )
                if contradicts:
                    new_row["冲突提示"] = (
                        f"补录凭据与已签署复核 {signed.get('复核编号')} 的结论「{signed_conclusion}」相反；"
                        "补证不改动历史结论，本事件另立待核查事项。"
                    )
                results.append({
                    "audit_id": audit.get("id"),
                    "记录编号": audit.get("记录编号"),
                    "review_id": new_row["id"],
                    "复核编号": new_row["复核编号"],
                    "处置": "形成该事件上另一次待核查事项",
                    "原复核编号": signed.get("复核编号"),
                    "结论变化": f"{signed_conclusion} → {new_row['审查结论']}",
                    "冲突提示": new_row["冲突提示"],
                })

            folded = any(item.get("处置") == "归入当前审查" for item in results)
            opened = any(item.get("处置") == "形成该事件上另一次待核查事项" for item in results)
            if folded and opened:
                message = "部分补录凭据归入当前审查，另有事件因原复核已签署而另立待核查事项"
            elif folded:
                message = "补录的同意凭据已归入该事件的当前审查"
            elif opened:
                message = "原复核已签署，补录凭据形成该事件上另一次待核查事项，历史结论不变"
            else:
                message = "补录记录未影响任何用途复核"
            return {"处置": message, "events": results, "说明": message}


purpose_review_service = PurposeReviewService()
