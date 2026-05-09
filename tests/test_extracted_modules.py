from copy import deepcopy

from backend.app import create_app
from backend.app.domain.doctor_schedules import DOCTOR_SCHEDULES
from backend.app.domain.triage_rules import DEPARTMENT_DETAILS
from backend.app.services.booking import book_appointment, list_departments
from backend.app.services.session_helpers import (
    build_assistant_reply,
    extract_patient_inputs,
    normalize_session_id,
)
from backend.app.state.sessions import build_session_payload


def test_create_app_registers_expected_config_and_routes():
    app = create_app()

    assert app.config["NORMALIZE_SESSION_ID"] is normalize_session_id
    assert app.config["EXTRACT_PATIENT_INPUTS"] is extract_patient_inputs
    assert app.config["BUILD_ASSISTANT_REPLY"] is build_assistant_reply

    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/chat" in routes
    assert "/api/appointments" in routes
    assert "/patient" in routes


def test_build_session_payload_fills_defaults_and_timestamp():
    payload = build_session_payload("demo-session")

    assert payload["sessionId"] == "demo-session"
    assert isinstance(payload["summary"], dict)
    assert payload["meta"] == {}
    assert payload["patientInputs"] == []
    assert isinstance(payload["updatedAt"], str)
    assert len(payload["updatedAt"]) >= 19


def test_extract_patient_inputs_marks_uploaded_images_and_truncates():
    long_text = "a" * 1300
    messages = [
        {"role": "assistant", "content": "ignore"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": long_text},
                {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
            ],
        },
    ]

    items = extract_patient_inputs(messages)

    assert len(items) == 1
    assert items[0]["hasImage"] is True
    assert len(items[0]["text"]) == 1200


def test_extract_patient_inputs_preserves_image_marker_when_text_is_short():
    items = extract_patient_inputs(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "咳嗽两天"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
                ],
            }
        ]
    )

    assert items == [{"text": "咳嗽两天\n[已上传图片]", "hasImage": True}]


def test_build_assistant_reply_uses_priority_specific_opening():
    urgent = build_assistant_reply({"triagePriority": "紧急", "nextQuestion": "请立刻去急诊。"})
    routine = build_assistant_reply({"triagePriority": "普通", "nextQuestion": "请补充年龄。"})

    assert "危险信号" in urgent
    assert urgent.endswith("请立刻去急诊。")
    assert routine == "我先帮你整理了一下关键信息。请补充年龄。"


def test_list_departments_aggregates_profiles_and_doctor_counts():
    schedules = deepcopy(DOCTOR_SCHEDULES)

    departments = list_departments(
        DEPARTMENT_DETAILS,
        schedules,
        build_department_profile=lambda name: {
            "location": f"{name}-loc",
            "waitTime": "10m",
            "overview": f"{name}-overview",
        },
    )

    respiratory = next(item for item in departments if item["name"] == "呼吸内科")
    assert respiratory["location"] == "呼吸内科-loc"
    assert respiratory["doctorCount"] >= 1


def test_book_appointment_raises_when_slots_full():
    schedules = {"测试科": [{"id": "d1", "name": "张医生", "title": "主任医师", "slots": 0}]}

    try:
        book_appointment(
            department="测试科",
            doctor_id="d1",
            patient_name="测试患者",
            doctor_schedules=schedules,
        )
    except ValueError as exc:
        assert "号源已满" in str(exc)
    else:
        raise AssertionError("expected ValueError when slots are full")


def test_normalize_session_id_strips_invalid_chars_and_falls_back():
    assert normalize_session_id("  abc-123_测试!!  ") == "abc-123_"
    assert normalize_session_id("!!!") == "default"
