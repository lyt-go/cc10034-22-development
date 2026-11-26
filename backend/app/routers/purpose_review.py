"""访问审计详情页的用途复核接口：提交、签署、补证与同意核对。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import (
    ActionResult,
    PurposeReviewCreate,
    PurposeReviewSign,
    PurposeReviewSupplement,
)
from app.services.purpose_review import purpose_review_service

router = APIRouter(prefix="/api/purpose_review", tags=["访问审计-用途复核"])

# 这些固定路径必须比 /{review_id} 更早注册，否则会被动态路径抢先匹配。
@router.get("/for-event/{audit_id}")
def event_packet(audit_id: int) -> dict[str, Any]:
    """详情页数据：审计事件、同意核对结果、该事件已有的用途复核。"""
    packet = purpose_review_service.event_packet(audit_id)
    if packet is None:
        raise HTTPException(status_code=404, detail=f"审计记录 {audit_id} 不存在或已归档")
    return packet


@router.post("/for-event/{audit_id}")
def submit_review(audit_id: int, payload: PurposeReviewCreate) -> ActionResult:
    """提交用途复核：服务端核对同意登记并出具历史用途单。"""
    entry, message, extra = purpose_review_service.submit(
        audit_id, operator=payload.operator, reason=payload.reason)
    return ActionResult(ok=entry is not None, message=message, entry=entry, extra=extra)


@router.get("")
def list_reviews(audit_id: int | None = None) -> dict[str, Any]:
    """复核列表；带 audit_id 时只返回该事件的复核。"""
    from app.store import store

    rows = store.rows("purpose_review")
    if audit_id is not None:
        rows = [row for row in rows if int(row.get("审计记录ID", 0)) == audit_id]
    return {"items": rows, "total": len(rows)}


@router.get("/{review_id}")
def get_review(review_id: int) -> dict[str, Any]:
    from app.store import store

    row = store.find("purpose_review", review_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"用途复核 {review_id} 不存在或已归档")
    return row


@router.post("/{review_id}/sign")
def sign_review(review_id: int, payload: PurposeReviewSign) -> ActionResult:
    """签署复核：只能引用访问时覆盖本事件处理目的的凭据。"""
    entry, message = purpose_review_service.sign(
        review_id,
        signer=payload.signer,
        consent_id=payload.consent_id,
        conclusion=payload.conclusion,
    )
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/{review_id}/supplement")
def supplement_review(review_id: int, payload: PurposeReviewSupplement) -> ActionResult:
    """补证复核：不改变已经签署的历史结论。"""
    entry, message, extra = purpose_review_service.supplement(
        review_id, operator=payload.operator, reason=payload.reason, evidence=payload.evidence)
    return ActionResult(ok=entry is not None, message=message, entry=entry, extra=extra)
