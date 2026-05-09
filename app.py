import io
import os
import uuid
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from flask import Flask

from backend.app.api.routes import bp as routes_bp
from backend.app.domain.doctor_schedules import DOCTOR_SCHEDULES
from backend.app.services.session_helpers import (
    build_assistant_reply,
    extract_patient_inputs,
    normalize_session_id,
)

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

DEPARTMENT_DETAILS: Dict[str, Dict[str, object]] = {
    "急诊科": {
        "overview": "24 小时接诊，优先处理胸痛、呼吸困难、意识异常等紧急症状。",
        "location": "急诊楼 1 层",
        "services": ["胸痛绿色通道", "卒中筛查", "危急重症分诊"],
        "tips": ["建议立即到院", "携带既往检查结果", "如胸痛持续请勿自行驾车"],
        "waitTime": "随到随分诊",
    },
    "心内科": {
        "overview": "主要评估胸痛、胸闷、心悸、高血压等心血管相关问题。",
        "location": "门诊楼 2 层",
        "services": ["心电图评估", "高血压随访", "胸痛门诊"],
        "tips": ["建议记录发作时间", "如胸痛加重先走急诊", "可携带既往心电图"],
        "waitTime": "约 25-40 分钟",
    },
    "呼吸内科": {
        "overview": "适合发热、咳嗽、咽痛、气短等呼吸系统症状的进一步评估。",
        "location": "门诊楼 3 层 A 区",
        "services": ["发热咳嗽分诊", "肺部感染评估", "慢性咳嗽门诊"],
        "tips": ["建议佩戴口罩", "可准备体温记录", "如气短明显请优先就近急诊"],
        "waitTime": "约 20-35 分钟",
    },
    "消化内科": {
        "overview": "主要处理腹痛、恶心、呕吐、腹泻、反酸等消化系统症状。",
        "location": "门诊楼 4 层 B 区",
        "services": ["腹痛评估", "胃肠炎门诊", "消化镜前咨询"],
        "tips": ["腹痛加重时避免自行进食", "可记录排便情况", "携带近期化验单更方便"],
        "waitTime": "约 20-30 分钟",
    },
    "普外科": {
        "overview": "适合右下腹痛、急腹症可疑、局部压痛明显等外科方向评估。",
        "location": "门诊楼 7 层急腹症单元",
        "services": ["急腹症筛查", "阑尾炎评估", "外科处置建议"],
        "tips": ["疼痛明显加重请尽快到院", "避免自行服止痛药掩盖病情", "如发热呕吐明显建议加急"],
        "waitTime": "约 10-20 分钟",
    },
    "神经内科": {
        "overview": "适用于头痛、头晕、肢体麻木无力等神经系统相关主诉。",
        "location": "门诊楼 5 层 A 区",
        "services": ["头痛门诊", "眩晕鉴别", "脑卒中早筛"],
        "tips": ["若伴口齿不清或偏瘫先去急诊", "建议描述起病时间", "可带既往头颅检查"],
        "waitTime": "约 25-40 分钟",
    },
    "皮肤科": {
        "overview": "适合皮疹、瘙痒、过敏反应和皮肤感染等情况。",
        "location": "门诊楼 1 层 C 区",
        "services": ["皮疹鉴别", "过敏评估", "皮肤感染门诊"],
        "tips": ["可上传/携带皮损照片", "近期外用药物请一并说明", "避免自行抓挠刺激"],
        "waitTime": "约 15-25 分钟",
    },
    "泌尿外科": {
        "overview": "适合尿频、尿急、尿痛、血尿或泌尿结石相关不适。",
        "location": "门诊楼 6 层 B 区",
        "services": ["泌尿感染门诊", "排尿异常评估", "结石随诊"],
        "tips": ["可记录排尿次数", "如伴高热腰痛请尽快就医", "携带尿检结果可提高效率"],
        "waitTime": "约 20-30 分钟",
    },
    "全科医学科": {
        "overview": "症状不够典型时可先由全科完成初筛，再转至更合适的专科。",
        "location": "门诊楼 1 层全科中心",
        "services": ["初诊分诊", "综合评估", "慢病随访建议"],
        "tips": ["适合首次就诊", "可先梳理主要不适", "带齐既往病历更方便二次转诊"],
        "waitTime": "约 15-20 分钟",
    },
    "耳鼻喉科": {
        "overview": "适合咽痛、鼻塞、耳痛、眩晕等耳鼻喉相关不适。",
        "location": "门诊楼 3 层 C 区",
        "services": ["咽喉检查", "鼻炎评估", "耳鸣耳痛门诊"],
        "tips": ["持续高热伴咽痛建议尽快就诊", "可说明是否夜间加重", "携带既往喉镜结果更方便"],
        "waitTime": "约 15-25 分钟",
    },
    "骨科": {
        "overview": "适合关节肿痛、扭伤、跌倒后疼痛与活动受限等情况。",
        "location": "门诊楼 6 层 A 区",
        "services": ["扭伤评估", "关节疼痛门诊", "运动损伤咨询"],
        "tips": ["若明显畸形建议急诊", "可描述受伤机制", "准备既往影像资料"],
        "waitTime": "约 20-35 分钟",
    },
    "内分泌科": {
        "overview": "适合血糖异常、甲状腺相关症状、体重波动和慢病随访。",
        "location": "门诊楼 5 层 B 区",
        "services": ["糖尿病随访", "甲状腺门诊", "代谢评估"],
        "tips": ["可带近期血糖记录", "空腹化验结果更方便", "慢病药物请一并说明"],
        "waitTime": "约 20-30 分钟",
    },
    "妇科": {
        "overview": "适合月经异常、下腹痛、白带异常等女性专科问题。",
        "location": "门诊楼 2 层 C 区",
        "services": ["月经异常评估", "盆腔不适门诊", "妇科炎症咨询"],
        "tips": ["急性剧痛或大量出血请尽快就诊", "可记录末次月经", "检查前避免自行用药"],
        "waitTime": "约 20-35 分钟",
    },
    "儿科": {
        "overview": "适合儿童发热、咳嗽、腹泻及常见急症的初步评估。",
        "location": "儿科门诊楼 2 层",
        "services": ["发热门诊", "儿童呼吸门诊", "儿童消化门诊"],
        "tips": ["请携带监护人证件", "可准备体温记录", "精神差明显请尽快就诊"],
        "waitTime": "约 20-30 分钟",
    },
}



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
    return summary


def build_assistant_reply(summary: Dict[str, object]) -> str:
    priority = str(summary.get("triagePriority", "普通"))
    next_question = str(summary.get("nextQuestion", "")).strip()

    opening = {
        "普通": "我先帮你整理了一下关键信息。",
        "尽快": "我已经提取了关键信息，你的情况建议尽快线下就诊。",
        "紧急": "我识别到了可能的危险信号，建议优先前往急诊或尽快寻求线下帮助。",
    }.get(priority, "我先帮你整理了一下关键信息。")

    return f"{opening}{next_question}"



app.config["NORMALIZE_SESSION_ID"] = normalize_session_id
app.config["EXTRACT_PATIENT_INPUTS"] = extract_patient_inputs
app.config["BUILD_ASSISTANT_REPLY"] = build_assistant_reply
app.register_blueprint(routes_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True, threaded=True)
