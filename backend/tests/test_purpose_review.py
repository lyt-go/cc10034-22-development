"""用途复核单元测试：访问时点判定、凭据引用约束、补证与补录归并。

运行：cd backend && .venv/bin/python -m pytest tests/test_purpose_review.py -v
"""
from __future__ import annotations

import pytest

from app.services.consent_registry import ConsentRegistryService
from app.services.purpose_review import (
    CONCLUSION_LATE,
    CONCLUSION_NONE,
    CONCLUSION_VALID,
    consent_check,
    parse_ts,
    purpose_review_service,
)
from app.store import store


@pytest.fixture(autouse=True)
def clean_store():
    """每条用例都从同一批种子数据出发，避免前一条用例的复核记录串场。"""
    store.reset()
    yield
    store.reset()


def _backfill(record: str, subject: str, purpose: str, signed: str, withdrawn: str = "未撤回"):
    service = ConsentRegistryService()
    entry, missing = service.create_entry({
        "记录编号": record,
        "数据主体": subject,
        "处理目的": purpose,
        "同意范围": "测试范围",
        "同意时间": signed,
        "撤回时间": withdrawn,
        "法律依据": "个人信息保护法第13条",
        "生效状态": "生效中",
    })
    assert missing == []
    service.create_effects(entry)
    return entry


# ——————————————— 访问时点判定 ———————————————


class TestConsentCheckAtAccessTime:
    def test_withdrawal_five_minutes_after_access_still_authorized(self):
        """上午十点访问、十分钟后撤回，不能判为当时无授权。"""
        consent = {
            "id": 4, "记录编号": "CONS-0004", "处理目的": "科研数据分析",
            "同意时间": "2026-11-25 09:00", "撤回时间": "2026-11-25 10:05",
            "status": "已撤回",
        }
        result = consent_check(consent, parse_ts("2026-11-25 10:00"), "科研数据分析")
        assert result["可用"] is True
        assert result["判定"] == "访问时有效"
        assert "5 分钟" in result["说明"]

    def test_withdrawal_before_access_is_invalid(self):
        consent = {
            "id": 2, "记录编号": "CONS-0002", "处理目的": "用户画像分析",
            "同意时间": "2026-08-15 08:30", "撤回时间": "2026-10-03 02:40",
            "status": "已撤回",
        }
        result = consent_check(consent, parse_ts("2026-10-03 03:15"), "用户画像分析")
        assert result["可用"] is False
        assert result["判定"] == "访问前已撤回"

    def test_withdrawal_at_exact_access_moment_is_invalid(self):
        """撤回时间与访问时间重合，按不晚于访问处理，授权已失效。"""
        consent = {
            "id": 9, "记录编号": "CONS-T9", "处理目的": "科研数据分析",
            "同意时间": "2026-09-01 09:00", "撤回时间": "2026-11-25 10:00",
            "status": "已撤回",
        }
        result = consent_check(consent, parse_ts("2026-11-25 10:00"), "科研数据分析")
        assert result["可用"] is False

    def test_other_purpose_consent_is_not_usable(self):
        """同一主体、其他用途的有效同意不能覆盖本次目的。"""
        consent = {
            "id": 1, "记录编号": "CONS-0001", "处理目的": "个性化推荐",
            "同意时间": "2026-10-01 09:00", "撤回时间": "未撤回", "status": "已同意",
        }
        result = consent_check(consent, parse_ts("2026-11-25 10:00"), "科研数据分析")
        assert result["可用"] is False
        assert result["判定"] == "处理目的不匹配"

    def test_late_signed_consent_is_not_retroactive(self):
        consent = {
            "id": 10, "记录编号": "CONS-T10", "处理目的": "科研数据分析",
            "同意时间": "2026-11-25 10:20", "撤回时间": "未撤回", "status": "已同意",
        }
        result = consent_check(consent, parse_ts("2026-11-25 10:00"), "科研数据分析")
        assert result["可用"] is False
        assert result["判定"] == "访问后才签署"


# ——————————————— 提交与出具用途单 ———————————————


class TestSubmitReview:
    def test_submit_issues_purpose_doc(self):
        row, message, extra = purpose_review_service.submit(1, operator="林可")
        assert row is not None, message
        assert row["status"] == "待签署"
        assert row["审查结论"] == CONCLUSION_VALID
        doc = row["用途单"]
        assert doc["单据编号"] == row["复核编号"]
        assert doc["判定"] == CONCLUSION_VALID
        assert doc["引用建议"] == "CONS-0004"
        assert [node["节点"] for node in doc["时间线"]] == ["同意签署", "访问发生", "同意撤回"]
        assert extra["候选同意"] == ["CONS-0004"]

    def test_submit_no_consent_reports_none(self):
        row, message, extra = purpose_review_service.submit(2, operator="周言")
        assert row is not None, message
        assert row["审查结论"] == CONCLUSION_NONE
        assert extra["候选同意"] == []

    def test_second_submit_folds_into_open_review(self):
        first, _, _ = purpose_review_service.submit(1, operator="林可")
        second, message, extra = purpose_review_service.submit(1, operator="许工")
        assert second["id"] == first["id"]
        assert extra["处置"] == "归入当前审查"
        assert len(purpose_review_service.reviews_for_event(1)) == 1

    def test_submit_after_signed_opens_new_review(self):
        first, _, _ = purpose_review_service.submit(1, operator="林可")
        purpose_review_service.sign(first["id"], signer="林可", consent_id=4)
        second, message, extra = purpose_review_service.submit(1, operator="许工")
        assert second["id"] != first["id"]
        assert extra["处置"].startswith("另立复核")
        assert len(purpose_review_service.reviews_for_event(1)) == 2

    def test_submit_missing_audit(self):
        row, message, extra = purpose_review_service.submit(9999)
        assert row is None
        assert "不存在" in message


# ——————————————— 签署约束 ———————————————


class TestSign:
    def test_sign_requires_citation_when_consent_exists(self):
        row, _, _ = purpose_review_service.submit(1)
        signed, message = purpose_review_service.sign(row["id"], signer="林可")
        assert signed is None
        assert "必须引用对应凭据" in message

    def test_sign_rejects_other_purpose_consent(self):
        row, _, _ = purpose_review_service.submit(1)
        signed, message = purpose_review_service.sign(row["id"], signer="林可", consent_id=1)
        assert signed is None
        assert "处理目的不匹配" in message or "不覆盖本次事件" in message

    def test_sign_accepts_covering_consent(self):
        row, _, _ = purpose_review_service.submit(1)
        signed, message = purpose_review_service.sign(row["id"], signer="林可", consent_id=4)
        assert signed is not None, message
        assert signed["status"] == "已签署"
        assert signed["引用同意"] == "CONS-0004"
        assert signed["用途单"]["引用建议"] == "CONS-0004"

    def test_sign_without_consent_when_none_exists(self):
        row, _, _ = purpose_review_service.submit(2)
        signed, message = purpose_review_service.sign(row["id"], signer="周言")
        assert signed is not None, message
        assert signed["引用同意"] == ""
        assert signed["审查结论"] == CONCLUSION_NONE

    def test_signed_review_cannot_be_signed_again(self):
        row, _, _ = purpose_review_service.submit(1)
        purpose_review_service.sign(row["id"], signer="林可", consent_id=4)
        again, message = purpose_review_service.sign(row["id"], signer="许工", consent_id=4)
        assert again is None
        assert "不可改动" in message

    def test_sign_requires_signer(self):
        row, _, _ = purpose_review_service.submit(1)
        signed, message = purpose_review_service.sign(row["id"], signer="  ", consent_id=4)
        assert signed is None
        assert "签署人" in message


# ——————————————— 补证 ———————————————


class TestSupplement:
    def test_supplement_on_open_review_folds_in(self):
        row, _, _ = purpose_review_service.submit(2)
        updated, message, extra = purpose_review_service.supplement(
            row["id"], operator="许工", reason="补充原始同意截图", evidence="IMG-01")
        assert updated is not None, message
        assert extra["处置"] == "归入当前审查"
        assert updated["status"] == "补证中"
        assert updated["补证记录"][-1]["原因"] == "补充原始同意截图"

    def test_supplement_requires_reason(self):
        row, _, _ = purpose_review_service.submit(2)
        updated, message, extra = purpose_review_service.supplement(row["id"], reason="  ")
        assert updated is None
        assert "补证原因" in message

    def test_supplement_on_signed_opens_new_review_and_freezes_original(self):
        row, _, _ = purpose_review_service.submit(1)
        signed, _ = purpose_review_service.sign(row["id"], signer="林可", consent_id=4)
        snapshot = dict(signed["签署存档"])
        new_row, message, extra = purpose_review_service.supplement(
            signed["id"], operator="许工", reason="补充公证材料", evidence="NOTARY-1")
        assert new_row is not None, message
        assert extra["处置"] == "形成该事件上另一次待核查事项"
        assert new_row["id"] != signed["id"]
        # 原签署记录必须完全不变
        assert signed["status"] == "已签署"
        assert signed["审查结论"] == snapshot["审查结论"]
        assert signed["引用同意"] == snapshot["引用同意"]
        assert signed["签署存档"] == snapshot
        assert signed["补证记录"] == []

    def test_supplement_after_signed_with_open_review_folds_into_open(self):
        """已签署后又另立了待核查事项，新补证应归入那次未落定的审查。"""
        row, _, _ = purpose_review_service.submit(1)
        purpose_review_service.sign(row["id"], signer="林可", consent_id=4)
        opened, _, _ = purpose_review_service.supplement(
            row["id"], operator="许工", reason="第一份补证")
        folded, message, extra = purpose_review_service.supplement(
            row["id"], operator="许工", reason="第二份补证")
        assert folded["id"] == opened["id"]
        assert extra["处置"] == "归入当前审查"


# ——————————————— 同意补录归并 ———————————————


class TestConsentBackfill:
    def test_backfill_into_open_review_changes_conclusion(self):
        """原复核尚未落定时，补录早先签署的同意归入当前审查。"""
        row, _, _ = purpose_review_service.submit(2)
        assert row["审查结论"] == CONCLUSION_NONE
        _backfill("CONS-0012", "user_5521098", "用户画像分析", "2026-09-30 08:00")
        assert row["status"] == "补证中"
        assert row["审查结论"] == CONCLUSION_VALID
        assert "CONS-0012" in row["用途单"]["引用建议"] or row["用途单"]["引用建议"] == "CONS-0012"
        assert "由「访问时未登记有效同意」变为" in row["冲突提示"]

    def test_backfill_after_signed_opens_another_pending_review(self):
        """原复核已签署时，补录形成另一次待核查事项，历史结论不变。"""
        row, _, _ = purpose_review_service.submit(2)
        signed, _ = purpose_review_service.sign(row["id"], signer="周言")
        signed_at = signed["签署时间"]
        _backfill("CONS-0013", "user_5521098", "用户画像分析", "2026-09-30 08:00")
        assert signed["status"] == "已签署"
        assert signed["审查结论"] == CONCLUSION_NONE
        assert signed["签署时间"] == signed_at
        reviews = purpose_review_service.reviews_for_event(2)
        assert len(reviews) == 2
        opened = reviews[-1]
        assert opened["status"] == "待签署"
        assert opened["关联审查ID"] == signed["id"]
        assert opened["审查结论"] == CONCLUSION_VALID
        assert "相反" in opened["冲突提示"]

    def test_backfill_of_late_consent_is_not_retroactive(self):
        """补录一份访问后才签署的同意，不能翻案为访问时有效。"""
        row, _, _ = purpose_review_service.submit(2)
        _backfill("CONS-0014", "user_5521098", "用户画像分析", "2026-10-03 09:00")
        assert row["审查结论"] == CONCLUSION_LATE
        assert row["用途单"]["判定"] == CONCLUSION_LATE
        assert row["用途单"]["引用建议"] == "CONS-0014"
        assert "不作为访问当时授权" in row["用途单"]["依据"]
        # 即便补录凭据已入库，签署时也不能把它当作访问时授权引用
        signed, message = purpose_review_service.sign(row["id"], signer="周言", consent_id=5)
        assert signed is None
        assert "访问后才签署" in message or "晚于访问时间" in message

    def test_backfill_without_matching_event_is_noop(self):
        result = purpose_review_service.on_consent_registered({
            "记录编号": "CONS-0099", "数据主体": "user_nobody",
            "处理目的": "科研数据分析", "同意时间": "2026-09-01 09:00",
            "撤回时间": "未撤回", "status": "已同意",
        })
        assert result["处置"] == "无需归并"
        assert store.rows("purpose_review") == []


# ——————————————— 两人交替提交 ———————————————


class TestAlternatingOperators:
    def test_two_operators_alternate_on_same_event(self):
        """模拟两名登记员/专员交替提交，核对签署凭据与后续补录。"""
        first, _, extra_one = purpose_review_service.submit(1, operator="专员-林可")
        assert extra_one["处置"] == "新建复核"

        # 另一名登记员补录一份访问前签署的同目的同意
        _backfill("CONS-0021", "user_1384729", "科研数据分析", "2026-08-20 09:00")
        assert first["status"] == "补证中"
        assert first["审查结论"] == CONCLUSION_VALID

        # 第一位专员签署，必须引用有效凭据
        rejected, message = purpose_review_service.sign(first["id"], signer="林可")
        assert rejected is None
        signed, message = purpose_review_service.sign(first["id"], signer="林可", consent_id=4)
        assert signed is not None, message
        assert signed["引用同意"] == "CONS-0004"

        # 第二名专员再次提交复核，不得改动原签署
        second, message, extra_two = purpose_review_service.submit(1, operator="专员-许工")
        assert extra_two["处置"].startswith("另立复核")
        assert second["id"] != signed["id"]
        assert signed["status"] == "已签署"
        assert signed["签署存档"]["引用同意"] == "CONS-0004"

        # 在第二笔复核上补证，仍不影响第一笔已签署结论
        signed_log_count = len(signed["补证记录"])
        updated, _, extra_three = purpose_review_service.supplement(
            second["id"], operator="林可", reason="补交访问截图")
        assert extra_three["处置"] == "归入当前审查"
        assert len(signed["补证记录"]) == signed_log_count
        assert signed["status"] == "已签署"
        # 补录凭据仍留在已签署复核的台账里，但签署结论与引用凭据不可被改写
        assert [log["类型"] for log in signed["补证记录"]] == ["补录凭据"]
