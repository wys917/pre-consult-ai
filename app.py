import json
import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)


SYMPTOM_PATTERNS: List[Tuple[str, List[str]]] = [
    ("发热", [r"发烧", r"发热", r"高热", r"低烧"]),
    ("咳嗽", [r"咳嗽"]),
    ("咽痛", [r"喉咙痛", r"咽痛", r"嗓子痛"]),
    ("流涕/鼻塞", [r"流鼻涕", r"鼻塞", r"鼻涕"]),
    ("乏力", [r"乏力", r"没劲", r"无力", r"疲劳"]),
    ("胸痛", [r"胸痛", r"胸口痛", r"心口痛"]),
    ("胸闷", [r"胸闷", r"胸口闷"]),
    ("呼吸困难", [r"呼吸困难", r"喘不上气", r"气短", r"呼吸费力"]),
    ("心悸", [r"心慌", r"心悸", r"心跳快", r"心率快"]),
    ("腹痛", [r"肚子疼", r"腹痛", r"胃痛", r"肚痛"]),
    ("恶心", [r"恶心", r"反胃"]),
    ("呕吐", [r"呕吐", r"吐了", r"吐"]),
    ("腹泻", [r"腹泻", r"拉肚子", r"稀便"]),
    ("头痛", [r"头痛"]),
    ("头晕", [r"头晕", r"眩晕", r"晕"]),
    ("肢体麻木/无力", [r"麻木", r"肢体无力", r"手脚无力", r"半边没劲"]),
    ("皮疹/瘙痒", [r"皮疹", r"起疹子", r"瘙痒", r"过敏"]),
    ("尿痛/尿频", [r"尿痛", r"尿频", r"尿急", r"小便痛"]),
    ("黑便/便血", [r"黑便", r"便血", r"大便带血"]),
    ("意识异常", [r"意识模糊", r"昏迷", r"说话不清", r"反应迟钝"]),
    ("晕厥", [r"晕倒", r"晕厥", r"昏过去"]),
    ("抽搐", [r"抽搐", r"抽风"]),
]

PRIORITY_LEVELS = {"普通": 0, "尽快": 1, "紧急": 2}

HISTORY_KEYWORDS = {
    "高血压": [r"高血压"],
    "糖尿病": [r"糖尿病"],
    "冠心病": [r"冠心病"],
    "哮喘": [r"哮喘"],
    "慢阻肺": [r"慢阻肺"],
    "脑卒中": [r"脑梗", r"脑卒中"],
}

DEPARTMENT_REASONS = {
    "急诊科": "存在紧急红旗征象，需优先急诊评估与处理。",
    "心内科": "症状涉及胸痛/心悸，建议优先心血管系统专科评估。",
    "呼吸内科": "症状集中在发热、咳嗽、咽痛或气短，符合呼吸系统就诊路径。",
    "消化内科": "主要表现为腹痛、恶心、呕吐或腹泻，优先消化系统评估。",
    "普外科": "腹痛位置提示外科急腹症风险，建议外科评估。",
    "神经内科": "头痛头晕或肢体神经症状突出，建议神经系统评估。",
    "皮肤科": "主要表现为皮疹/瘙痒等皮肤症状。",
    "泌尿外科": "主要表现为尿痛/尿频等泌尿系统症状。",
    "全科医学科": "当前症状不典型，建议先由全科进行初筛分诊。",
}

DOCTOR_SCHEDULES: Dict[str, List[Dict[str, object]]] = {
    "呼吸内科": [
        {"id": "resp-1", "name": "林晓明", "title": "主任医师", "intro": "擅长呼吸道感染、慢性咳嗽", "slots": 6},
        {"id": "resp-2", "name": "赵雨桐", "title": "副主任医师", "intro": "擅长哮喘、肺炎规范化诊疗", "slots": 4},
    ],
    "心内科": [
        {"id": "card-1", "name": "陈江", "title": "主任医师", "intro": "擅长胸痛中心流程和心衰管理", "slots": 3},
        {"id": "card-2", "name": "周敏", "title": "主治医师", "intro": "擅长心悸与高血压长期管理", "slots": 5},
    ],
    "消化内科": [
        {"id": "gi-1", "name": "王可", "title": "副主任医师", "intro": "擅长腹痛、消化道炎症诊疗", "slots": 5},
        {"id": "gi-2", "name": "徐杰", "title": "主治医师", "intro": "擅长胃肠功能紊乱和早筛", "slots": 7},
    ],
    "神经内科": [
        {"id": "neuro-1", "name": "刘畅", "title": "主任医师", "intro": "擅长头痛门诊和脑卒中随访", "slots": 4}
    ],
    "皮肤科": [
        {"id": "derm-1", "name": "沈雅", "title": "主治医师", "intro": "擅长过敏性皮炎与皮疹诊治", "slots": 6}
    ],
    "泌尿外科": [
        {"id": "uro-1", "name": "高远", "title": "副主任医师", "intro": "擅长泌尿感染和结石诊治", "slots": 5}
    ],
    "普外科": [
        {"id": "surg-1", "name": "唐浩", "title": "主任医师", "intro": "擅长急腹症与微创外科", "slots": 2}
    ],
    "急诊科": [
        {"id": "er-1", "name": "急诊值班团队", "title": "24小时接诊", "intro": "危重症快速评估与处置", "slots": 999}
    ],
    "全科医学科": [
        {"id": "gp-1", "name": "何楠", "title": "主治医师", "intro": "擅长初诊分诊与慢病管理", "slots": 8}
    ],
}


def bump_priority(current: str, target: str) -> str:
    return target if PRIORITY_LEVELS[target] > PRIORITY_LEVELS[current] else current


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def combined_user_text(messages: List[Dict[str, object]]) -> str:
    user_parts = []
    for m in messages:
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                user_parts.append(content)
            elif isinstance(content, list):
                # 从多模态列表中提取纯文本部分供正则引擎使用
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
        return clean[:18] + ("…" if len(clean) > 18 else "") if clean else "待补充"

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


def analyze_conversation(messages: List[Dict[str, str]]) -> Dict[str, object]:
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

    accompanying = symptoms[1:5] if len(symptoms) > 1 else []

    has_image = any(
        isinstance(m.get("content"), list)
        for m in messages if m.get("role") == "user"
    )
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
        "imageFindings": "检测到已上传图片，但当前处于 Mock 规则模式，无法解析图像内容，请切换至 API 模式。" if has_image else "未提供影像",
    }
    summary["doctorSummary"] = build_doctor_summary(summary, age)
    return summary


def build_assistant_reply(summary: Dict[str, object]) -> str:
    priority = summary.get("triagePriority", "普通")
    next_question = summary.get("nextQuestion", "")

    opening = {
        "普通": "我先帮你整理了一下关键信息。",
        "尽快": "我已经提取了关键信息，你的情况建议尽快线下就诊。",
        "紧急": "我识别到了可能的危险信号，建议优先前往急诊或尽快寻求线下帮助。",
    }.get(priority, "我先帮你整理了一下关键信息。")

    return f"{opening}{next_question}"


SYSTEM_PROMPT = """你是一个具备视觉能力的门诊预问诊助手。你的任务不是给出最终诊断，而是：
1. 分析患者对话和上传的图片（如皮疹、化验单等），提取结构化病历摘要。
2. 识别红旗征象并给出分诊优先级。
3. 推荐就诊科室。
4. 继续提出下一轮最关键的追问。

请务必以 JSON 返回，且字段严格为：
chiefComplaint, duration, accompanyingSymptoms, redFlags, recommendedDepartment, departmentReason, triagePriority, missingInformation, nextQuestion, doctorSummary, pastHistory, allergyHistory, medicationHistory, consistencyAlerts, imageFindings

约束：
- imageFindings: 对上传图片的客观描述（如"见红色斑丘疹"），如果没有图片则返回"未提供影像"。
- triagePriority 只能是：普通 / 尽快 / 紧急
- 不要给出确定性诊断
- 输出内容必须是合法 JSON，不要使用 Markdown 代码块
"""

def call_deepseek_api(messages: List[Dict[str, str]]) -> Dict[str, object]:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    base_url = os.getenv("DEEPSEEK_BASE_URL", "").strip()
    model_name = os.getenv("DEEPSEEK_MODEL", "").strip()

    if not api_key or not base_url or not model_name:
        raise RuntimeError(
            "尚未配置 DeepSeek 接口。请在 .env 中填写 DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL、DEEPSEEK_MODEL。"
        )

    payload = {
        "model": model_name,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = base_url.rstrip("/") + "/chat/completions"
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
        # 清理可能包含的 Markdown 代码块标记
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        elif clean_content.startswith("```"):
            clean_content = clean_content[3:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        clean_content = clean_content.strip()
        
        summary = json.loads(clean_content)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("模型返回结果无法解析为 JSON，请检查提示词或接口配置。") from exc

    for key, default_value in {
        "departmentReason": "根据现有症状综合判断。",
        "pastHistory": [],
        "allergyHistory": "待补充",
        "medicationHistory": "待补充",
        "consistencyAlerts": [],
        "imageFindings": "未提供影像",
    }.items():
        summary.setdefault(key, default_value)

    if "doctorSummary" not in summary:
        summary["doctorSummary"] = build_doctor_summary(summary, "")
    summary["_model"] = model_name
    return summary


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
        
        # 允许 content 是字符串或列表（多模态）
        if not content:
             raise ValueError(f"messages[{index}].content 不能为空")

        validated.append({"role": role, "content": content})

    return validated

def list_department_doctors(department: str) -> List[Dict[str, object]]:
    return DOCTOR_SCHEDULES.get(department, [])


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    mode = data.get("mode", "mock")

    try:
        messages = validate_messages(messages)

        if mode == "api":
            summary = call_deepseek_api(messages)
            source = "api"
            model_name = str(summary.pop("_model", "unknown"))
        else:
            summary = analyze_conversation(messages)
            source = "mock"
            model_name = "rule-based"

        reply = build_assistant_reply(summary)
        return jsonify({"reply": reply, "summary": summary, "source": source, "model": model_name})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.HTTPError as exc:
        return jsonify({"error": f"调用模型接口失败：{exc.response.text}"}), 502
    except requests.RequestException as exc:
        return jsonify({"error": f"调用模型接口异常：{str(exc)}"}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.get("/api/departments/<department>/doctors")
def api_department_doctors(department: str):
    doctors = list_department_doctors(department)
    if not doctors:
        return jsonify({"error": "该科室暂无排班信息"}), 404
    return jsonify({"department": department, "date": datetime.now().strftime("%Y-%m-%d"), "doctors": doctors})


@app.post("/api/appointments")
def api_appointments():
    data = request.get_json(silent=True) or {}
    department = str(data.get("department", "")).strip()
    doctor_id = str(data.get("doctorId", "")).strip()
    patient_name = str(data.get("patientName", "")).strip() or "患者"

    if not department or not doctor_id:
        return jsonify({"error": "department 和 doctorId 为必填"}), 400

    doctors = list_department_doctors(department)
    for doctor in doctors:
        if doctor.get("id") == doctor_id:
            if int(doctor.get("slots", 0)) <= 0:
                return jsonify({"error": "该医生号源已满，请选择其他医生"}), 409
            if doctor_id != "er-1":
                doctor["slots"] = int(doctor["slots"]) - 1
            return jsonify(
                {
                    "success": True,
                    "appointmentId": f"APT-{uuid.uuid4().hex[:8].upper()}",
                    "message": f"{patient_name} 挂号成功，已预约 {doctor['name']}（{doctor['title']}）。",
                    "department": department,
                    "doctor": doctor,
                }
            )

    return jsonify({"error": "未找到对应医生"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
