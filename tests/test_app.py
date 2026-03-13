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
    assert "departmentProfile" in summary
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
    assert payload["departmentProfile"]["location"] == "门诊楼 3 层 A 区"
    assert len(payload["doctors"]) >= 1


def test_departments_list_returns_multiple_departments(client):
    response = client.get("/api/departments")

    assert response.status_code == 200
    payload = response.get_json()
    names = {item["name"] for item in payload["departments"]}
    assert "呼吸内科" in names
    assert "耳鼻喉科" in names


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


def test_api_chat_deepseek_provider_uses_selected_channel(client, monkeypatch):
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": """
                            {
                              "chiefComplaint": "发热咳嗽3天",
                              "duration": "3天",
                              "accompanyingSymptoms": ["咽痛"],
                              "redFlags": [],
                              "recommendedDepartment": "呼吸内科",
                              "departmentReason": "症状与呼吸系统相关",
                              "triagePriority": "普通",
                              "missingInformation": ["年龄"],
                              "nextQuestion": "请补充年龄。",
                              "doctorSummary": "建议前往呼吸内科。",
                              "pastHistory": [],
                              "allergyHistory": "待补充",
                              "medicationHistory": "待补充",
                              "consistencyAlerts": [],
                              "imageFindings": "未提供影像"
                            }
                            """
                        }
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setattr("app.requests.post", fake_post)

    response = client.post(
        "/api/chat",
        json={
            "provider": "deepseek",
            "messages": [{"role": "user", "content": "我发烧咳嗽三天"}],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["provider"] == "deepseek"
    assert payload["providerLabel"] == "DeepSeek"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-deepseek-key"
    assert captured["payload"]["model"] == "deepseek-chat"


def test_export_pdf_returns_pdf_bytes(client):
    response = client.post(
        "/api/export/pdf",
        json={
            "summary": {
                "chiefComplaint": "发热咳嗽3天",
                "duration": "3天",
                "accompanyingSymptoms": ["咽痛", "乏力"],
                "redFlags": [],
                "recommendedDepartment": "呼吸内科",
                "departmentReason": "呼吸系统相关症状",
                "triagePriority": "普通",
                "missingInformation": [],
                "doctorSummary": "建议前往呼吸内科。",
                "pastHistory": [],
                "allergyHistory": "否认明确过敏史",
                "medicationHistory": "近期未自行用药",
                "consistencyAlerts": [],
                "imageFindings": "未提供影像",
            }
        },
    )

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/pdf"
    assert response.data.startswith(b"%PDF")
