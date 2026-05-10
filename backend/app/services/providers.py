import json
import os
import re
from typing import Callable, Dict, List

import requests

from backend.app.domain.provider_config import MODEL_PROVIDERS, SUMMARY_DEFAULTS, SYSTEM_PROMPT


class ProviderConfigurationError(RuntimeError):
    pass


def get_provider_settings(provider: str) -> Dict[str, object]:
    config = MODEL_PROVIDERS.get(provider)
    if not config:
        raise ValueError("不支持的模型通道")

    prefix = str(config["env_prefix"])
    legacy_prefix = str(config.get("legacy_env_prefix", ""))

    def read_setting(field: str) -> str:
        value = os.getenv(f"{prefix}_{field}", "").strip()
        if value:
            return value
        if legacy_prefix:
            return os.getenv(f"{legacy_prefix}_{field}", "").strip()
        return ""

    api_key = read_setting("API_KEY")
    if not api_key:
        raise ProviderConfigurationError(f"尚未配置{config['label']}接口，请检查 .env 中的 {prefix}_API_KEY。")

    base_url = read_setting("BASE_URL") or str(config["default_base_url"])
    model_name = read_setting("MODEL") or str(config["default_model"])

    return {
        **config,
        "api_key": api_key,
        "base_url": base_url,
        "model_name": model_name,
    }


def adapt_messages_for_provider(messages: List[Dict[str, object]], supports_multimodal: bool) -> List[Dict[str, object]]:
    if supports_multimodal:
        return messages

    adapted: List[Dict[str, object]] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            adapted.append({"role": message["role"], "content": content})
            continue

        text_parts: List[str] = []
        image_count = 0
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")).strip())
                elif item.get("type") == "image_url":
                    image_count += 1

        if image_count:
            text_parts.append(
                f"患者还上传了 {image_count} 张图片，但当前模型通道不支持直接解析影像，请在 imageFindings 中说明未解析影像。"
            )

        adapted.append(
            {
                "role": message["role"],
                "content": "\n".join(part for part in text_parts if part) or "患者上传了图片，请结合文本继续追问。",
            }
        )
    return adapted


def parse_json_content(content: str) -> Dict[str, object]:
    clean_content = (content or "").strip()
    if clean_content.startswith("```json"):
        clean_content = clean_content[7:]
    elif clean_content.startswith("```"):
        clean_content = clean_content[3:]
    if clean_content.endswith("```"):
        clean_content = clean_content[:-3]
    clean_content = clean_content.strip()

    try:
        return json.loads(clean_content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean_content, re.S)
        if match:
            return json.loads(match.group(0))
        raise


def normalize_model_summary(
    summary: Dict[str, object],
    has_image: bool,
    provider_settings: Dict[str, object],
    *,
    build_doctor_summary: Callable[[Dict[str, object], str], str],
    build_department_profile: Callable[[str], Dict[str, object]],
) -> Dict[str, object]:
    normalized = dict(SUMMARY_DEFAULTS)
    normalized.update(summary)

    for key in ["accompanyingSymptoms", "redFlags", "missingInformation", "pastHistory", "consistencyAlerts"]:
        value = normalized.get(key)
        if isinstance(value, list):
            normalized[key] = [str(item).strip() for item in value if str(item).strip()]
        elif value:
            normalized[key] = [str(value).strip()]
        else:
            normalized[key] = []

    if normalized.get("triagePriority") not in {"普通", "尽快", "紧急"}:
        normalized["triagePriority"] = "待判断"

    if has_image and not provider_settings.get("supports_multimodal"):
        normalized["imageFindings"] = "检测到已上传图片，但当前所选模型通道不支持直接解析影像。"
    elif not has_image and not str(normalized.get("imageFindings", "")).strip():
        normalized["imageFindings"] = "未提供影像"

    if not str(normalized.get("doctorSummary", "")).strip():
        normalized["doctorSummary"] = build_doctor_summary(normalized, "")

    department = str(normalized.get("recommendedDepartment", "")).strip()
    if not isinstance(normalized.get("departmentProfile"), dict) or not normalized.get("departmentProfile"):
        normalized["departmentProfile"] = build_department_profile(department)

    return normalized


def call_model_api(
    provider: str,
    messages: List[Dict[str, object]],
    *,
    contains_uploaded_image: Callable[[List[Dict[str, object]]], bool],
    build_doctor_summary: Callable[[Dict[str, object], str], str],
    build_department_profile: Callable[[str], Dict[str, object]],
) -> Dict[str, object]:
    provider_settings = get_provider_settings(provider)
    adapted_messages = adapt_messages_for_provider(messages, bool(provider_settings["supports_multimodal"]))

    payload = {
        "model": provider_settings["model_name"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + adapted_messages,
        "temperature": 0.2,
        "stream": False,
    }
    if provider_settings.get("supports_json_format"):
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {provider_settings['api_key']}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        str(provider_settings["base_url"]).rstrip("/") + "/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
        summary = parse_json_content(content)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("模型返回结果无法解析为 JSON，请检查提示词或接口配置。") from exc

    normalized = normalize_model_summary(
        summary,
        contains_uploaded_image(messages),
        provider_settings,
        build_doctor_summary=build_doctor_summary,
        build_department_profile=build_department_profile,
    )
    normalized["_model"] = provider_settings["model_name"]
    normalized["_provider"] = provider
    normalized["_provider_label"] = provider_settings["label"]
    return normalized
