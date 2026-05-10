import re
from typing import Dict, List, Tuple

from backend.app.domain.defaults import DEFAULT_SESSION_ID


def normalize_session_id(value: object) -> str:
    session_id = str(value or "").strip()
    if not session_id:
        return DEFAULT_SESSION_ID

    session_id = re.sub(r"[^a-zA-Z0-9_-]+", "", session_id)[:64]
    return session_id or DEFAULT_SESSION_ID


def normalize_patient_content(content: object) -> Tuple[str, bool]:
    if isinstance(content, str):
        return content.strip(), False

    if isinstance(content, list):
        texts: List[str] = []
        has_image = False
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).strip().lower()
            if item_type == "text":
                text_part = str(item.get("text", "")).strip()
                if text_part:
                    texts.append(text_part)
            elif item_type in {"image_url", "image"}:
                has_image = True

        return "\n".join(texts).strip(), has_image

    return str(content).strip(), False


def extract_patient_inputs(messages: List[Dict[str, object]]) -> List[Dict[str, object]]:
    inputs: List[Dict[str, object]] = []
    for message in messages:
        if message.get("role") != "user":
            continue

        text, has_image = normalize_patient_content(message.get("content"))
        display_text = text
        if has_image:
            display_text = f"{text}\n[已上传图片]" if text else "[已上传图片]"

        display_text = display_text.strip()
        if not display_text:
            continue

        inputs.append(
            {
                "text": display_text[:1200],
                "hasImage": has_image,
            }
        )

    return inputs[-30:]


def build_assistant_reply(summary: Dict[str, object]) -> str:
    priority = str(summary.get("triagePriority", "普通"))
    next_question = str(summary.get("nextQuestion", "")).strip()

    opening = {
        "普通": "我先帮你整理了一下关键信息。",
        "尽快": "我已经提取了关键信息，你的情况建议尽快线下就诊。",
        "紧急": "我识别到了可能的危险信号，建议优先前往急诊或尽快寻求线下帮助。",
    }.get(priority, "我先帮你整理了一下关键信息。")

    return f"{opening}{next_question}"
