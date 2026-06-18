from datetime import datetime
from queue import Empty, Queue
from typing import Dict, List

import requests
from flask import Blueprint, Response, current_app, jsonify, make_response, redirect, render_template, request, stream_with_context, url_for

from backend.app.domain.doctor_schedules import DOCTOR_SCHEDULES
from backend.app.domain.triage_rules import DEPARTMENT_DETAILS
from backend.app.services.booking import (
    book_appointment,
    generate_summary_pdf,
    list_department_doctors,
    list_departments,
)
from backend.app.services.case_queue import (
    STATUS_LABELS as CASE_STATUS_LABELS,
    build_case_queue,
    build_case_row,
)
from backend.app.services.providers import call_model_api
from backend.app.services.workflow import enrich_summary_workflow
from backend.app.services.triage import (
    analyze_conversation,
    build_department_profile,
    build_doctor_summary,
    contains_uploaded_image,
)
from backend.app.state.sessions import (
    SESSION_LOCK,
    SESSION_STATES,
    SESSION_SUBSCRIBERS,
    build_session_payload,
    publish_session_event,
    sse_encode,
)

bp = Blueprint("main", __name__)


def validate_messages(messages: object) -> List[Dict[str, object]]:
    if not isinstance(messages, list):
        raise ValueError("messages 必须为数组")

    validated: List[Dict[str, object]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"messages[{index}] 必须为对象")

        role = message.get("role")
        content = message.get("content")

        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"messages[{index}].role 非法")
        if not content:
            raise ValueError(f"messages[{index}].content 不能为空")

        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    raise ValueError(f"messages[{index}].content 中存在非法项")

        validated.append({"role": role, "content": content})

    return validated


def resolve_provider(data: Dict[str, object]) -> str:
    provider = str(data.get("provider", "")).strip().lower()
    mode = str(data.get("mode", "")).strip().lower()

    if provider:
        if provider == "api":
            return "doubao"
        return provider
    if mode == "mock":
        return "mock"
    if mode == "api":
        return "doubao"
    return "doubao"


def normalize_session_id(value: object) -> str:
    normalizer = current_app.config["NORMALIZE_SESSION_ID"]
    return normalizer(value)


def extract_patient_inputs(messages: List[Dict[str, object]]) -> List[Dict[str, object]]:
    extractor = current_app.config["EXTRACT_PATIENT_INPUTS"]
    return extractor(messages)


def build_assistant_reply(summary: Dict[str, object]) -> str:
    builder = current_app.config["BUILD_ASSISTANT_REPLY"]
    return builder(summary)


def list_department_doctors_local(department: str) -> List[Dict[str, object]]:
    return list_department_doctors(department, DOCTOR_SCHEDULES)


def list_departments_local() -> List[Dict[str, object]]:
    return list_departments(
        DEPARTMENT_DETAILS,
        DOCTOR_SCHEDULES,
        build_department_profile=build_department_profile,
    )


@bp.route("/")
def index():
    return redirect(url_for("main.patient_view"))


@bp.get("/combined")
def combined_view():
    return render_template("index.html")


@bp.get("/patient")
def patient_view():
    return render_template("patient.html")


@bp.get("/doctor")
def doctor_view():
    return render_template("doctor.html")


@bp.get("/doctor/queue")
def doctor_queue_view():
    return render_template("doctor_queue.html")


@bp.get("/api/cases")
def api_case_queue():
    status_filter = request.args.get("status") or None
    with SESSION_LOCK:
        snapshot = {sid: dict(state) for sid, state in SESSION_STATES.items()}
    cases = build_case_queue(snapshot, status_filter=status_filter)
    return jsonify(
        {
            "cases": cases,
            "total": len(cases),
            "statusLabels": CASE_STATUS_LABELS,
        }
    )


@bp.get("/api/cases/<session_id>")
def api_case_detail(session_id: str):
    session_id = normalize_session_id(session_id)
    with SESSION_LOCK:
        state = SESSION_STATES.get(session_id)
        state_copy = dict(state) if isinstance(state, dict) else None
    if not state_copy:
        return jsonify({"error": "未找到会话"}), 404
    row = build_case_row(session_id, state_copy)
    return jsonify({"case": row, "state": state_copy})


@bp.get("/api/sessions/<session_id>/stream")
def api_session_stream(session_id: str):
    session_id = normalize_session_id(session_id)
    queue: Queue = Queue(maxsize=25)

    with SESSION_LOCK:
        SESSION_SUBSCRIBERS.setdefault(session_id, []).append(queue)
        initial = SESSION_STATES.get(session_id) or build_session_payload(session_id)

    def event_stream():
        try:
            yield sse_encode("state", initial)

            while True:
                try:
                    packet = queue.get(timeout=15)
                except Empty:
                    yield ": keep-alive\n\n"
                    continue

                event = str(packet.get("event", "update"))
                payload = packet.get("payload")
                if not isinstance(payload, dict):
                    continue

                yield sse_encode(event, payload)
        finally:
            with SESSION_LOCK:
                subscribers = SESSION_SUBSCRIBERS.get(session_id, [])
                if queue in subscribers:
                    subscribers.remove(queue)
                if not subscribers:
                    SESSION_SUBSCRIBERS.pop(session_id, None)

    response = Response(stream_with_context(event_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@bp.post("/api/sessions/<session_id>/reset")
def api_session_reset(session_id: str):
    session_id = normalize_session_id(session_id)
    payload = build_session_payload(session_id)

    with SESSION_LOCK:
        SESSION_STATES[session_id] = payload

    publish_session_event(session_id, "reset", payload)
    return jsonify({"success": True, **payload})


@bp.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    session_id = normalize_session_id(data.get("sessionId"))
    provider = resolve_provider(data)

    try:
        messages = validate_messages(messages)
        patient_inputs = extract_patient_inputs(messages)

        if provider == "mock":
            summary = analyze_conversation(messages)
            source = "mock"
            model_name = "rule-based"
            provider_label = "Mock 规则引擎"
        else:
            summary = call_model_api(
                provider,
                messages,
                contains_uploaded_image=contains_uploaded_image,
                build_doctor_summary=build_doctor_summary,
                build_department_profile=build_department_profile,
            )
            source = "api"
            model_name = str(summary.pop("_model", "unknown"))
            provider_label = str(summary.pop("_provider_label", provider))
            summary.pop("_provider", None)

        session_payload = build_session_payload(
            session_id,
            summary=summary,
            meta={
                "source": source,
                "provider": provider,
                "providerLabel": provider_label,
                "model": model_name,
            },
            patient_inputs=patient_inputs,
        )
        with SESSION_LOCK:
            SESSION_STATES[session_id] = session_payload
        publish_session_event(session_id, "update", session_payload)

        reply = build_assistant_reply(summary)
        return jsonify(
            {
                "reply": reply,
                "summary": summary,
                "source": source,
                "model": model_name,
                "provider": provider,
                "providerLabel": provider_label,
                "sessionId": session_id,
                "updatedAt": session_payload["updatedAt"],
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        return jsonify({"error": f"调用模型接口失败：{detail}"}), 502
    except requests.RequestException as exc:
        return jsonify({"error": f"调用模型接口异常：{str(exc)}"}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/departments/<department>/doctors")
def api_department_doctors(department: str):
    doctors = list_department_doctors_local(department)
    if not doctors:
        return jsonify({"error": "该科室暂无排班信息"}), 404
    return jsonify(
        {
            "department": department,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "departmentProfile": build_department_profile(department),
            "doctors": doctors,
        }
    )


@bp.get("/api/departments")
def api_departments():
    return jsonify({"departments": list_departments_local()})


@bp.post("/api/appointments")
def api_appointments():
    data = request.get_json(silent=True) or {}
    department = str(data.get("department", "")).strip()
    doctor_id = str(data.get("doctorId", "")).strip()
    patient_name = str(data.get("patientName", "")).strip() or "患者"
    session_id = normalize_session_id(data.get("sessionId"))

    if not department or not doctor_id:
        return jsonify({"error": "department 和 doctorId 为必填"}), 400

    try:
        result = book_appointment(
            department=department,
            doctor_id=doctor_id,
            patient_name=patient_name,
            doctor_schedules=DOCTOR_SCHEDULES,
        )

        with SESSION_LOCK:
            existing = SESSION_STATES.get(session_id) or build_session_payload(session_id)
            summary = dict(existing.get("summary") or {})
            summary["recommendedDepartment"] = department or summary.get("recommendedDepartment", "待判断")
            summary["bookingStatus"] = "booked"
            summary["bookingRecord"] = {
                "appointmentId": result.get("appointmentId", ""),
                "department": result.get("department", department),
                "doctorName": (result.get("doctor") or {}).get("name", ""),
                "schedule": (result.get("doctor") or {}).get("schedule", ""),
            }
            session_payload = build_session_payload(
                session_id,
                summary=summary,
                meta=existing.get("meta") if isinstance(existing.get("meta"), dict) else {},
                patient_inputs=existing.get("patientInputs") if isinstance(existing.get("patientInputs"), list) else [],
            )
            SESSION_STATES[session_id] = session_payload

        publish_session_event(session_id, "update", session_payload)
        return jsonify({**result, "sessionId": session_id, "summary": session_payload["summary"]})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    except LookupError:
        return jsonify({"error": "未找到对应医生"}), 404


@bp.post("/api/export/pdf")
def api_export_pdf():
    data = request.get_json(silent=True) or {}
    summary = data.get("summary")
    if not isinstance(summary, dict):
        return jsonify({"error": "summary 必须为对象"}), 400

    try:
        pdf_bytes = generate_summary_pdf(summary)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    filename = f"triage-summary-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf"
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Content-Length"] = str(len(pdf_bytes))
    return response
