"""Doctor-side case queue projection.

Phase 3.1 groundwork: derive a queue-of-cases view from in-memory session
states so the doctor workbench can triage multiple sessions instead of
rendering a single summary page.
"""

from __future__ import annotations

from typing import Dict, List, Optional


PRIORITY_RANK = {
    "紧急": 0,
    "尽快": 1,
    "普通": 2,
    "待判断": 3,
}


STAGE_TO_STATUS = {
    "urgent_handoff": "escalated",
    "booked": "booked",
    "ready_for_booking": "ready_for_booking",
    "ready_for_triage": "in_review",
    "collecting": "in_review",
}


STATUS_LABELS = {
    "new": "新会话",
    "in_review": "待分诊",
    "ready_for_booking": "待挂号",
    "escalated": "紧急转诊",
    "booked": "已挂号",
    "closed": "已关闭",
    "manual_review": "需人工复核",
}


def _safe_dict(value: object) -> Dict[str, object]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: object) -> List[object]:
    return value if isinstance(value, list) else []


def derive_case_status(summary: Dict[str, object], patient_inputs: List[object]) -> str:
    """Map workflow stage + review flags to a concrete queue status."""
    stage = str(summary.get("workflowStage") or "collecting")

    if not patient_inputs and stage == "collecting":
        return "new"

    if bool(summary.get("needsManualReview")):
        return "manual_review"

    return STAGE_TO_STATUS.get(stage, "in_review")


def _priority_rank(priority: str) -> int:
    return PRIORITY_RANK.get(priority, PRIORITY_RANK["待判断"])


def build_case_row(session_id: str, state: Dict[str, object]) -> Dict[str, object]:
    """Project a single session state into a queue row."""
    summary = _safe_dict(state.get("summary"))
    meta = _safe_dict(state.get("meta"))
    patient_inputs = _safe_list(state.get("patientInputs"))

    priority = str(summary.get("triagePriority") or "待判断")
    status = derive_case_status(summary, patient_inputs)
    needs_manual_review = bool(summary.get("needsManualReview"))

    return {
        "sessionId": session_id,
        "status": status,
        "statusLabel": STATUS_LABELS.get(status, status),
        "chiefComplaint": summary.get("chiefComplaint") or "待补充",
        "recommendedDepartment": summary.get("recommendedDepartment") or "待判断",
        "triagePriority": priority,
        "workflowStage": summary.get("workflowStage") or "collecting",
        "workflowStageLabel": summary.get("workflowStageLabel") or "信息采集中",
        "lifecycleState": summary.get("lifecycleState") or "intake_started",
        "needsManualReview": needs_manual_review,
        "reviewReason": summary.get("reviewReason") or "",
        "riskSource": summary.get("riskSource") or "rule",
        "confidenceScore": float(summary.get("confidenceScore") or 0.0),
        "redFlags": list(summary.get("redFlags") or []),
        "missingInformation": list(summary.get("missingInformation") or []),
        "updatedAt": state.get("updatedAt") or "",
        "turns": len(patient_inputs),
        "provider": meta.get("provider") or "",
        "providerLabel": meta.get("providerLabel") or "",
        "model": meta.get("model") or "",
    }


def sort_key(row: Dict[str, object]) -> tuple:
    """Risk-first ordering: urgent → manual review → priority → newest updated."""
    stage = str(row.get("workflowStage") or "")
    is_urgent = 0 if stage == "urgent_handoff" else 1
    needs_review = 0 if row.get("needsManualReview") else 1
    priority = _priority_rank(str(row.get("triagePriority") or "待判断"))
    # Invert updatedAt so newer comes first with ascending sort.
    updated_at = str(row.get("updatedAt") or "")
    updated_key = tuple(-ord(c) for c in updated_at)
    return (is_urgent, needs_review, priority, updated_key)


def build_case_queue(
    session_states: Dict[str, Dict[str, object]],
    *,
    status_filter: Optional[str] = None,
) -> List[Dict[str, object]]:
    rows = [build_case_row(session_id, state) for session_id, state in session_states.items()]
    if status_filter:
        rows = [row for row in rows if row.get("status") == status_filter]
    rows.sort(key=sort_key)
    return rows
