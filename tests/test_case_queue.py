from copy import deepcopy

import pytest

from app import app
from backend.app.services.case_queue import (
    STATUS_LABELS,
    build_case_queue,
    build_case_row,
    derive_case_status,
)
from backend.app.state.sessions import SESSION_LOCK, SESSION_STATES, build_session_payload


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def clean_sessions():
    with SESSION_LOCK:
        snapshot = deepcopy(SESSION_STATES)
        SESSION_STATES.clear()
    yield
    with SESSION_LOCK:
        SESSION_STATES.clear()
        SESSION_STATES.update(snapshot)


def _seed_state(
    session_id,
    *,
    summary_overrides=None,
    patient_inputs=None,
    meta=None,
    updated_at="2026-05-10T03:00:00",
):
    summary = {
        "chiefComplaint": "发热咳嗽",
        "recommendedDepartment": "呼吸内科",
        "triagePriority": "尽快",
        "missingInformation": [],
        "accompanyingSymptoms": ["发热", "咳嗽"],
        "redFlags": [],
        "pastHistory": [],
        "imageFindings": "未提供影像",
    }
    summary.update(summary_overrides or {})
    payload = build_session_payload(
        session_id,
        summary=summary,
        meta=meta or {"provider": "mock", "providerLabel": "Mock 规则引擎", "model": "rule-based"},
        patient_inputs=patient_inputs if patient_inputs is not None else [{"role": "user", "content": "demo"}],
        updated_at=updated_at,
    )
    with SESSION_LOCK:
        SESSION_STATES[session_id] = payload
    return payload


def test_derive_case_status_detects_manual_review():
    summary = {"workflowStage": "collecting", "needsManualReview": True}
    assert derive_case_status(summary, [{"role": "user"}]) == "manual_review"


def test_derive_case_status_maps_booked_stage():
    summary = {"workflowStage": "booked", "needsManualReview": False}
    assert derive_case_status(summary, [{"role": "user"}]) == "booked"


def test_derive_case_status_marks_empty_session_as_new():
    summary = {"workflowStage": "collecting"}
    assert derive_case_status(summary, []) == "new"


def test_build_case_row_projects_key_fields():
    payload = _seed_state(
        "case-1",
        summary_overrides={"redFlags": ["持续胸痛"], "triagePriority": "紧急", "recommendedDepartment": "急诊科"},
    )
    row = build_case_row("case-1", payload)
    assert row["sessionId"] == "case-1"
    assert row["triagePriority"] == "紧急"
    assert row["redFlags"] == ["持续胸痛"]
    assert row["statusLabel"] in STATUS_LABELS.values()
    assert row["providerLabel"] == "Mock 规则引擎"


def test_build_case_queue_sorts_urgent_before_manual_review_before_normal():
    _seed_state(
        "c-normal",
        summary_overrides={"triagePriority": "普通", "recommendedDepartment": "消化内科"},
        updated_at="2026-05-10T02:00:00",
    )
    _seed_state(
        "c-manual",
        summary_overrides={
            "triagePriority": "普通",
            "recommendedDepartment": "全科医学科",
            "accompanyingSymptoms": ["胸痛"],
        },
        updated_at="2026-05-10T02:30:00",
    )
    _seed_state(
        "c-urgent",
        summary_overrides={
            "triagePriority": "紧急",
            "recommendedDepartment": "急诊科",
            "redFlags": ["持续胸痛"],
            "accompanyingSymptoms": ["胸痛"],
        },
        updated_at="2026-05-10T01:00:00",
    )

    with SESSION_LOCK:
        snapshot = {sid: dict(state) for sid, state in SESSION_STATES.items()}

    queue = build_case_queue(snapshot)
    order = [row["sessionId"] for row in queue]
    assert order.index("c-urgent") < order.index("c-manual") < order.index("c-normal")


def test_build_case_queue_supports_status_filter():
    _seed_state("c-normal", summary_overrides={"triagePriority": "普通"})
    _seed_state(
        "c-urgent",
        summary_overrides={"triagePriority": "紧急", "redFlags": ["持续胸痛"], "accompanyingSymptoms": ["胸痛"]},
    )
    with SESSION_LOCK:
        snapshot = {sid: dict(state) for sid, state in SESSION_STATES.items()}
    queue = build_case_queue(snapshot, status_filter="escalated")
    assert len(queue) == 1
    assert queue[0]["sessionId"] == "c-urgent"


def test_api_cases_returns_ordered_queue(client):
    _seed_state("c-normal", summary_overrides={"triagePriority": "普通"})
    _seed_state(
        "c-urgent",
        summary_overrides={
            "triagePriority": "紧急",
            "redFlags": ["持续胸痛"],
            "accompanyingSymptoms": ["胸痛"],
        },
    )

    response = client.get("/api/cases")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 2
    assert data["cases"][0]["sessionId"] == "c-urgent"
    assert "statusLabels" in data


def test_api_cases_status_filter(client):
    _seed_state(
        "c-review",
        summary_overrides={
            "triagePriority": "普通",
            "recommendedDepartment": "全科医学科",
            "accompanyingSymptoms": ["胸痛"],
        },
    )
    _seed_state("c-normal", summary_overrides={"triagePriority": "普通"})

    response = client.get("/api/cases?status=manual_review")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["cases"][0]["sessionId"] == "c-review"
    assert data["cases"][0]["needsManualReview"] is True


def test_api_case_detail_returns_single_row(client):
    _seed_state("c-detail")
    response = client.get("/api/cases/c-detail")
    assert response.status_code == 200
    data = response.get_json()
    assert data["case"]["sessionId"] == "c-detail"
    assert data["state"]["sessionId"] == "c-detail"


def test_api_case_detail_404_for_unknown(client):
    response = client.get("/api/cases/does-not-exist")
    assert response.status_code == 404


def test_doctor_queue_view_renders(client):
    response = client.get("/doctor/queue")
    assert response.status_code == 200
    assert "案例队列 Workbench" in response.get_data(as_text=True)
