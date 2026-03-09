import json
import os
import re
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


def bump_priority(current: str, target: str) -> str:
    return target if PRIORITY_LEVELS[target] > PRIORITY_LEVELS[current] else current


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def combined_user_text(messages: List[Dict[str, str]]) -> str:
    user_parts = [m.get("content", "") for m in messages if m.get("role") == "user"]
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
    text = normalize_text(combined_user_text(messages))
    age = extract_age(text)
    duration = extract_duration(text)
    temperature = extract_temperature(text)
    symptoms = ordered_detected_symptoms(text)
    red_flags, priority = detect_red_flags(text, symptoms, temperature)
    department = recommend_department(text, symptoms, priority)
    missing = build_missing_information(text, symptoms, duration, age, temperature)
    chief_complaint = build_chief_complaint(symptoms, duration, text)

    if len(symptoms) <= 1:
        accompanying = []
    else:
        accompanying = symptoms[1:5]

    summary: Dict[str, object] = {
        "chiefComplaint": chief_complaint,
        "duration": duration or "待补充",
        "accompanyingSymptoms": accompanying,
        "redFlags": red_flags,
        "recommendedDepartment": department,
        "triagePriority": priority,
        "missingInformation": missing,
        "nextQuestion": next_question_from_missing(missing, symptoms),
        "doctorSummary": "",
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


SYSTEM_PROMPT = """你是一个门诊预问诊助手。你的任务不是给出最终诊断，而是：
1. 从患者对话中提取结构化病历摘要。
2. 识别红旗征象并给出分诊优先级。
3. 推荐就诊科室。
4. 继续提出下一轮最关键的追问。

请务必以 JSON 返回，且字段严格为：
chiefComplaint, duration, accompanyingSymptoms, redFlags, recommendedDepartment, triagePriority, missingInformation, nextQuestion, doctorSummary

约束：
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
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(base_url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
        summary = json.loads(content)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("模型返回结果无法解析为 JSON，请检查提示词或接口配置。") from exc

    if "doctorSummary" not in summary:
        summary["doctorSummary"] = build_doctor_summary(summary, "")
    return summary


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    mode = data.get("mode", "mock")

    if not isinstance(messages, list):
        return jsonify({"error": "messages 必须为数组"}), 400

    try:
        if mode == "api":
            summary = call_deepseek_api(messages)
        else:
            summary = analyze_conversation(messages)

        reply = build_assistant_reply(summary)
        return jsonify({"reply": reply, "summary": summary})
    except requests.HTTPError as exc:
        return jsonify({"error": f"调用模型接口失败：{exc.response.text}"}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
