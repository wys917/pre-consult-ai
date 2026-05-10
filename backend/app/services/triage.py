import re
from typing import Dict, List, Tuple

from backend.app.domain.triage_rules import (
    DEPARTMENT_DETAILS,
    DEPARTMENT_REASONS,
    HISTORY_KEYWORDS,
    PRIORITY_LEVELS,
    SYMPTOM_PATTERNS,
)


def bump_priority(current: str, target: str) -> str:
    return target if PRIORITY_LEVELS[target] > PRIORITY_LEVELS[current] else current


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def combined_user_text(messages: List[Dict[str, object]]) -> str:
    user_parts = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            user_parts.append(content)
            continue
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    user_parts.append(item.get("text", ""))
    return "\n".join(user_parts)


def extract_duration(text: str) -> str:
    patterns = [
        r"([一二两三四五六七八九十半\d]+\s*(?:分钟|小时|天|周|星期|个月|月|年))",
        r"(昨天)",
        r"(今天)",
        r"(前天)",
        r"(这两天)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).replace(" ", "")
    return ""


def extract_age(text: str) -> str:
    patterns = [
        r"(\d{1,3})\s*岁",
        r"今年(\d{1,3})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)}岁"
    return ""


def extract_temperature(text: str) -> str:
    match = re.search(r"([3-4]\d(?:\.\d)?)\s*度", text)
    return match.group(1) if match else ""


def extract_past_history(text: str) -> List[str]:
    result = []
    for label, patterns in HISTORY_KEYWORDS.items():
        if any(re.search(pattern, text) for pattern in patterns):
            result.append(label)
    return result


def extract_allergy_history(text: str) -> str:
    if re.search(r"无过敏|不过敏|没有过敏", text):
        return "否认明确过敏史"
    match = re.search(r"(?:对|有)([^，。；\s]{1,12})(?:过敏)", text)
    if match:
        return f"{match.group(1)}过敏"
    if "过敏" in text:
        return "有过敏史（具体待补充）"
    return "待补充"


def extract_medication_history(text: str) -> str:
    if re.search(r"没吃药|未用药|没有用药", text):
        return "近期未自行用药"
    matches = re.findall(r"(?:吃了|服用|用了)([^，。；\s]{1,12})", text)
    if matches:
        return "、".join(dict.fromkeys(matches))
    return "待补充"


def ordered_detected_symptoms(text: str) -> List[str]:
    hits: List[Tuple[int, str]] = []
    for label, patterns in SYMPTOM_PATTERNS:
        min_pos = None
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if min_pos is None or match.start() < min_pos:
                    min_pos = match.start()
        if min_pos is not None:
            hits.append((min_pos, label))
    hits.sort(key=lambda item: item[0])
    return [label for _, label in hits]


def detect_red_flags(text: str, symptoms: List[str], temperature: str) -> Tuple[List[str], str]:
    red_flags: List[str] = []
    priority = "普通"

    if "胸痛" in symptoms and "呼吸困难" in symptoms:
        red_flags.append("胸痛伴呼吸困难")
        priority = bump_priority(priority, "紧急")
    elif "胸痛" in symptoms:
        red_flags.append("出现胸痛，需排除心血管急症")
        priority = bump_priority(priority, "尽快")

    if "晕厥" in symptoms or "意识异常" in symptoms or "抽搐" in symptoms:
        red_flags.append("存在意识/神经系统危险信号")
        priority = bump_priority(priority, "紧急")

    if "肢体麻木/无力" in symptoms and "头痛" in symptoms:
        red_flags.append("头痛伴肢体无力/麻木")
        priority = bump_priority(priority, "紧急")

    if re.search(r"右下腹", text) and "腹痛" in symptoms:
        red_flags.append("右下腹痛，需排除阑尾炎等急腹症")
        priority = bump_priority(priority, "尽快")

    if re.search(r"剧痛|很痛|特别痛|疼得厉害|越来越痛|走路都痛|不能走路", text) and "腹痛" in symptoms:
        red_flags.append("腹痛程度较重")
        priority = bump_priority(priority, "尽快")

    if temperature:
        try:
            if float(temperature) >= 39.0:
                red_flags.append("高热")
                priority = bump_priority(priority, "尽快")
        except ValueError:
            pass

    if "黑便/便血" in symptoms:
        red_flags.append("黑便/便血")
        priority = bump_priority(priority, "尽快")

    return red_flags, priority


def recommend_department(text: str, symptoms: List[str], priority: str) -> str:
    if priority == "紧急":
        return "急诊科"
    if "胸痛" in symptoms or "心悸" in symptoms:
        return "心内科"
    if "呼吸困难" in symptoms and "咳嗽" in symptoms:
        return "呼吸内科"
    if "咳嗽" in symptoms or "咽痛" in symptoms or "发热" in symptoms or "流涕/鼻塞" in symptoms:
        return "呼吸内科"
    if "腹痛" in symptoms:
        if re.search(r"右下腹", text):
            return "普外科"
        return "消化内科"
    if "头痛" in symptoms or "头晕" in symptoms or "肢体麻木/无力" in symptoms:
        return "神经内科"
    if "皮疹/瘙痒" in symptoms:
        return "皮肤科"
    if "尿痛/尿频" in symptoms:
        return "泌尿外科"
    return "全科医学科"


def build_missing_information(text: str, symptoms: List[str], duration: str, age: str, temperature: str) -> List[str]:
    missing: List[str] = []
    if not age:
        missing.append("年龄")
    if not duration:
        missing.append("症状持续时间")
    if "发热" in symptoms and not temperature:
        missing.append("最高体温")
    if "胸痛" in symptoms and not re.search(r"呼吸困难|大汗|放射|左臂|下颌", text):
        missing.append("是否伴呼吸困难/大汗/放射痛")
    if "腹痛" in symptoms and not re.search(r"右下腹|左下腹|上腹|下腹|肚脐周围|胃部", text):
        missing.append("腹痛部位")
    if "咳嗽" in symptoms and not re.search(r"咳痰|痰|呼吸困难|气短", text):
        missing.append("是否咳痰或气短")
    if "头痛" in symptoms and not re.search(r"视物模糊|麻木|无力|恶心|呕吐", text):
        missing.append("是否伴视物模糊/麻木/呕吐")
    return missing


def next_question_from_missing(missing: List[str], symptoms: List[str]) -> str:
    if not missing:
        return "目前关键信息基本齐全，我已经在右侧整理出结构化病历摘要。"
    if "是否伴呼吸困难/大汗/放射痛" in missing:
        return "请问胸痛时是否伴有呼吸困难、大汗，或者向左肩、左臂、下颌放射的疼痛？"
    if "腹痛部位" in missing:
        return "请问腹痛主要位于上腹、下腹、右下腹还是肚脐周围？疼痛是在加重还是缓解？"
    if "最高体温" in missing:
        return "请问最高体温大概是多少度？除了发热外，有没有明显怕冷、咳嗽或气短？"
    if "是否咳痰或气短" in missing:
        return "请问咳嗽时有没有痰，或者是否感觉气短、呼吸费力？"
    if "是否伴视物模糊/麻木/呕吐" in missing:
        return "请问头痛时有没有视物模糊、肢体麻木无力，或者明显恶心呕吐？"
    if missing[:2] == ["年龄", "症状持续时间"]:
        return "请先告诉我你的年龄，以及这些症状大概持续了多久。"
    if "年龄" in missing:
        return "请先告诉我你的年龄，方便我进一步判断就诊优先级。"
    if "症状持续时间" in missing:
        return "这些症状大概持续了多久，是突然出现还是逐渐加重的？"
    return f"为了继续完善预问诊信息，请补充：{'、'.join(missing[:2])}。"


def build_chief_complaint(symptoms: List[str], duration: str, text: str) -> str:
    if not symptoms:
        clean = re.sub(r"\s+", "", text)
        return clean[:18] + ("..." if len(clean) > 18 else "") if clean else "待补充"

    chief_parts = symptoms[:2]
    complaint = "、".join(chief_parts)
    if duration:
        complaint += duration
    return complaint


def detect_consistency_alerts(raw_text: str) -> List[str]:
    alerts: List[str] = []
    if re.search(r"不发烧|没发烧|无发热", raw_text) and re.search(r"发烧|发热|[3-4]\d(?:\.\d)?度", raw_text):
        alerts.append("体温描述前后不一致（既提到无发热又提到发热/高温）")
    if re.search(r"不咳嗽|没有咳嗽", raw_text) and re.search(r"咳嗽", raw_text):
        alerts.append("咳嗽症状前后描述不一致")
    if re.search(r"不腹痛|没有腹痛", raw_text) and re.search(r"腹痛|肚子疼|胃痛", raw_text):
        alerts.append("腹痛症状前后描述不一致")
    if re.search(r"今天", raw_text) and re.search(r"[三四五六七八九十\d]+天", raw_text):
        alerts.append("症状起病时间描述可能冲突（今天 vs 多天）")
    return alerts


def build_doctor_summary(summary: Dict[str, object], age: str) -> str:
    subject = f"患者{age}，" if age else "患者，"
    chief = summary.get("chiefComplaint") or "主诉待补充"
    companions = summary.get("accompanyingSymptoms") or []
    red_flags = summary.get("redFlags") or []
    department = summary.get("recommendedDepartment") or "待判断"
    priority = summary.get("triagePriority") or "待判断"

    companion_text = "、".join(companions) if companions else "暂无明确伴随症状"
    red_flag_text = "、".join(red_flags) if red_flags else "暂未识别明显红旗征象"

    return (
        f"{subject}当前主诉为“{chief}”。伴随症状：{companion_text}。"
        f"红旗征象：{red_flag_text}。建议优先前往{department}就诊，分诊优先级为“{priority}”。"
    )


def build_department_profile(department: str) -> Dict[str, object]:
    info = DEPARTMENT_DETAILS.get(
        department,
        {
            "overview": "该科室适合进一步进行专科评估。",
            "location": "门诊分诊台咨询",
            "services": ["专科评估", "基础检查建议"],
            "tips": ["请结合现场分诊建议"],
            "waitTime": "以当日号源为准",
        },
    )
    return {
        "name": department or "待判断",
        "overview": info["overview"],
        "location": info["location"],
        "services": list(info["services"]),
        "tips": list(info["tips"]),
        "waitTime": info["waitTime"],
    }


def contains_uploaded_image(messages: List[Dict[str, object]]) -> bool:
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    return True
    return False


from backend.app.services.workflow import enrich_summary_workflow


def analyze_conversation(messages: List[Dict[str, object]]) -> Dict[str, object]:
    raw_text = combined_user_text(messages)
    text = normalize_text(raw_text)
    age = extract_age(text)
    duration = extract_duration(text)
    temperature = extract_temperature(text)
    symptoms = ordered_detected_symptoms(text)
    red_flags, priority = detect_red_flags(text, symptoms, temperature)
    department = recommend_department(text, symptoms, priority)
    missing = build_missing_information(text, symptoms, duration, age, temperature)
    chief_complaint = build_chief_complaint(symptoms, duration, text)
    past_history = extract_past_history(text)
    allergy_history = extract_allergy_history(text)
    medication_history = extract_medication_history(text)
    consistency_alerts = detect_consistency_alerts(raw_text)
    has_image = contains_uploaded_image(messages)

    accompanying = symptoms[1:5] if len(symptoms) > 1 else []

    summary: Dict[str, object] = {
        "chiefComplaint": chief_complaint,
        "duration": duration or "待补充",
        "accompanyingSymptoms": accompanying,
        "redFlags": red_flags,
        "recommendedDepartment": department,
        "departmentReason": DEPARTMENT_REASONS.get(department, "根据现有症状综合判断。"),
        "triagePriority": priority,
        "missingInformation": missing,
        "nextQuestion": next_question_from_missing(missing, symptoms),
        "doctorSummary": "",
        "pastHistory": past_history,
        "allergyHistory": allergy_history,
        "medicationHistory": medication_history,
        "consistencyAlerts": consistency_alerts,
        "departmentProfile": build_department_profile(department),
        "imageFindings": (
            "检测到已上传图片，但当前处于 Mock 规则模式，无法解析图像内容，请切换至支持视觉的模型。"
            if has_image
            else "未提供影像"
        ),
    }
    summary["doctorSummary"] = build_doctor_summary(summary, age)
    return enrich_summary_workflow(summary)
