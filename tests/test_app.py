from copy import deepcopy

import pytest

from app import DOCTOR_SCHEDULES, app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def restore_schedules():
    original = deepcopy(DOCTOR_SCHEDULES)
    yield
    DOCTOR_SCHEDULES.clear()
    DOCTOR_SCHEDULES.update(original)


def test_api_chat_mock_returns_extended_summary_fields(client):
    response = client.post(
        "/api/chat",
        json={
            "mode": "mock",
            "messages": [{"role": "user", "content": "我45岁，有高血压，青霉素过敏，发烧39度并咳嗽三天"}],
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    summary = data["summary"]

    assert data["source"] == "mock"
    assert summary["recommendedDepartment"] == "呼吸内科"
    assert "pastHistory" in summary
    assert "allergyHistory" in summary
    assert "medicationHistory" in summary
    assert "departmentReason" in summary
    assert "consistencyAlerts" in summary


def test_api_chat_rejects_invalid_message_role(client):
    response = client.post(
        "/api/chat",
        json={"mode": "mock", "messages": [{"role": "invalid", "content": "test"}]},
    )

    assert response.status_code == 400
    assert "role 非法" in response.get_json()["error"]


def test_department_doctors_returns_schedule(client):
    response = client.get("/api/departments/呼吸内科/doctors")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["department"] == "呼吸内科"
    assert len(payload["doctors"]) >= 1


def test_appointments_decrement_slots(client):
    before = client.get("/api/departments/呼吸内科/doctors").get_json()["doctors"]
    doctor_id = before[0]["id"]
    before_slots = before[0]["slots"]

    response = client.post(
        "/api/appointments",
        json={"department": "呼吸内科", "doctorId": doctor_id, "patientName": "测试用户"},
    )

    assert response.status_code == 200
    result = response.get_json()
    assert result["success"] is True
    assert result["appointmentId"].startswith("APT-")

    after = client.get("/api/departments/呼吸内科/doctors").get_json()["doctors"]
    after_slots = next(d["slots"] for d in after if d["id"] == doctor_id)
    assert after_slots == before_slots - 1


def test_appointments_missing_fields_returns_400(client):
    response = client.post("/api/appointments", json={"department": "呼吸内科"})

    assert response.status_code == 400
    assert "必填" in response.get_json()["error"]
