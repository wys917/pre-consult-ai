import json
from queue import Full, Queue
from threading import Lock
from typing import Dict, List, Optional

from backend.app.domain.defaults import new_default_summary

SESSION_STATES: Dict[str, Dict[str, object]] = {}
SESSION_SUBSCRIBERS: Dict[str, List[Queue]] = {}
SESSION_LOCK = Lock()


def build_session_payload(
    session_id: str,
    *,
    summary: Optional[Dict[str, object]] = None,
    meta: Optional[Dict[str, object]] = None,
    patient_inputs: Optional[List[Dict[str, object]]] = None,
    updated_at: str = "",
) -> Dict[str, object]:
    return {
        "sessionId": session_id,
        "summary": summary if isinstance(summary, dict) else new_default_summary(),
        "meta": meta if isinstance(meta, dict) else {},
        "patientInputs": patient_inputs if isinstance(patient_inputs, list) else [],
        "updatedAt": updated_at,
    }


def publish_session_event(session_id: str, event: str, payload: Dict[str, object]) -> None:
    with SESSION_LOCK:
        subscribers = list(SESSION_SUBSCRIBERS.get(session_id, []))

    packet = {"event": event, "payload": payload}
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(packet)
        except Full:
            try:
                subscriber.get_nowait()
                subscriber.put_nowait(packet)
            except Exception:
                continue


def sse_encode(event: str, payload: Dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
