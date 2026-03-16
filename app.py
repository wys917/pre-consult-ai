import io
import json
import os
import re
import uuid
from datetime import datetime
from queue import Empty, Full, Queue
from threading import Lock
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, make_response, redirect, render_template, request, stream_with_context, url_for

load_dotenv()

app = Flask(__name__)

DEFAULT_SESSION_ID = "default"


def normalize_session_id(value: object) -> str:
    session_id = str(value or "").strip()
    if not session_id:
        return DEFAULT_SESSION_ID

    # Keep it URL-friendly and avoid accidental huge keys.
    session_id = re.sub(r"[^a-zA-Z0-9_-]+", "", session_id)[:64]
    return session_id or DEFAULT_SESSION_ID


def new_default_summary() -> Dict[str, object]:
    return {
        "chiefComplaint": "待补充",
        "duration": "待补充",
        "accompanyingSymptoms": [],
        "redFlags": [],
        "recommendedDepartment": "待判断",
        "departmentReason": "待补充",
        "triagePriority": "待判断",
        "missingInformation": [],
        "nextQuestion": "",
        "doctorSummary": "患者信息尚未完善，等待对话开始。",
        "pastHistory": [],
        "allergyHistory": "待补充",
        "medicationHistory": "待补充",
        "consistencyAlerts": [],
        "imageFindings": "未提供影像",
        "departmentProfile": {},
    }


SESSION_STATES: Dict[str, Dict[str, object]] = {}
SESSION_SUBSCRIBERS: Dict[str, List[Queue]] = {}
SESSION_LOCK = Lock()


def build_session_payload(
    session_id: str,
    *,
    summary: Optional[Dict[str, object]] = None,
    meta: Optional[Dict[str, object]] = None,
    patient_inputs: Optional[List[Dict[str, object]]] = None,
) -> Dict[str, object]:
    return {
        "sessionId": session_id,
        "summary": summary if isinstance(summary, dict) else new_default_summary(),
        "meta": meta if isinstance(meta, dict) else {},
        "patientInputs": patient_inputs if isinstance(patient_inputs, list) else [],
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }


def publish_session_event(session_id: str, event: str, payload: Dict[str, object]) -> None:
    with SESSION_LOCK:
        subscribers = list(SESSION_SUBSCRIBERS.get(session_id, []))

    packet = {"event": event, "payload": payload}
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(packet)
        except Full:
            # Drop the oldest event to keep the stream fresh.
            try:
                subscriber.get_nowait()
                subscriber.put_nowait(packet)
            except Exception:  # noqa: BLE001
                continue


def sse_encode(event: str, payload: Dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


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

MODEL_PROVIDERS: Dict[str, Dict[str, object]] = {
    "doubao": {
        "label": "豆包",
        "env_prefix": "DOUBAO",
        "legacy_env_prefix": "DEEPSEEK",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-seed-2-0-pro-260215",
        "supports_multimodal": True,
        "supports_json_format": False,
    },
    "deepseek": {
        "label": "DeepSeek",
        "env_prefix": "DEEPSEEK",
        "legacy_env_prefix": "",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "supports_multimodal": False,
        "supports_json_format": True,
    },
}

DOCTOR_SCHEDULES: Dict[str, List[Dict[str, object]]] = {
    "呼吸内科": [
        {
            "id": "resp-1",
            "name": "钱黄瀚",
            "title": "主任医师",
            "intro": "擅长呼吸道感染、慢性咳嗽与肺部炎症分层管理。",
            "specialty": "发热、咳嗽、肺部感染",
            "schedule": "09:00-11:30",
            "slots": 6,
            "fee": 58,
            "location": "门诊楼 3 层 A 区",
        },
        {
            "id": "resp-2",
            "name": "吴承鸿",
            "title": "副主任医师",
            "intro": "擅长哮喘、肺炎和呼吸困难的规范化评估。",
            "specialty": "哮喘、肺炎、气短",
            "schedule": "13:30-16:30",
            "slots": 4,
            "fee": 42,
            "location": "门诊楼 3 层 A 区",
        },
        {
            "id": "resp-3",
            "name": "冯知遥",
            "title": "主治医师",
            "intro": "擅长上呼吸道感染、咽痛与门诊雾化治疗评估。",
            "specialty": "咽痛、气道炎症、雾化评估",
            "schedule": "18:00-20:30",
            "slots": 8,
            "fee": 26,
            "location": "门诊楼 3 层夜间门诊",
        },
    ],
    "心内科": [
        {
            "id": "card-1",
            "name": "陈江文",
            "title": "主任医师",
            "intro": "擅长胸痛中心流程、心衰管理与高危胸闷评估。",
            "specialty": "胸痛、胸闷、心衰",
            "schedule": "08:30-11:30",
            "slots": 3,
            "fee": 68,
            "location": "门诊楼 2 层 VIP 诊区",
        },
        {
            "id": "card-2",
            "name": "周敏霞",
            "title": "主治医师",
            "intro": "擅长心悸、高血压与心电图异常门诊随访。",
            "specialty": "心悸、高血压",
            "schedule": "14:00-17:00",
            "slots": 5,
            "fee": 36,
            "location": "门诊楼 2 层 B 区",
        },
        {
            "id": "card-3",
            "name": "顾安澜",
            "title": "副主任医师",
            "intro": "擅长胸闷胸痛初筛、动态血压与冠脉危险因素评估。",
            "specialty": "胸闷、胸痛、血压异常",
            "schedule": "18:00-20:00",
            "slots": 6,
            "fee": 48,
            "location": "门诊楼 2 层晚间门诊",
        },
    ],
    "消化内科": [
        {
            "id": "gi-1",
            "name": "王乐可",
            "title": "副主任医师",
            "intro": "擅长腹痛、消化道炎症及胃肠镜前评估。",
            "specialty": "腹痛、反酸、胃肠炎",
            "schedule": "09:00-12:00",
            "slots": 5,
            "fee": 45,
            "location": "门诊楼 4 层 B 区",
        },
        {
            "id": "gi-2",
            "name": "徐懂杰",
            "title": "主治医师",
            "intro": "擅长胃肠功能紊乱、恶心呕吐与早筛咨询。",
            "specialty": "恶心、腹泻、胃肠功能紊乱",
            "schedule": "13:30-16:30",
            "slots": 7,
            "fee": 32,
            "location": "门诊楼 4 层 B 区",
        },
        {
            "id": "gi-3",
            "name": "周闻溪",
            "title": "住院总医师",
            "intro": "擅长急性胃肠炎、腹泻与轻中度腹痛的快速评估。",
            "specialty": "腹泻、恶心、胃肠炎",
            "schedule": "17:30-20:00",
            "slots": 9,
            "fee": 18,
            "location": "门诊楼 4 层便民门诊",
        },
    ],
    "神经内科": [
        {
            "id": "neuro-1",
            "name": "刘畅",
            "title": "主任医师",
            "intro": "擅长头痛门诊、脑卒中早筛与眩晕鉴别。",
            "specialty": "头痛、头晕、麻木",
            "schedule": "08:30-11:30",
            "slots": 4,
            "fee": 62,
            "location": "门诊楼 5 层 A 区",
        }
    ],
    "皮肤科": [
        {
            "id": "derm-1",
            "name": "沈雅",
            "title": "主治医师",
            "intro": "擅长过敏性皮炎、皮疹和瘙痒的快速鉴别。",
            "specialty": "皮疹、瘙痒、过敏",
            "schedule": "10:00-16:00",
            "slots": 6,
            "fee": 34,
            "location": "门诊楼 1 层 C 区",
        }
    ],
    "泌尿外科": [
        {
            "id": "uro-1",
            "name": "王宇",
            "title": "副主任医师",
            "intro": "擅长泌尿感染、结石与排尿异常评估。",
            "specialty": "尿频、尿痛、结石",
            "schedule": "13:00-17:00",
            "slots": 5,
            "fee": 46,
            "location": "门诊楼 6 层 B 区",
        }
    ],
    "普外科": [
        {
            "id": "surg-1",
            "name": "赵忆成",
            "title": "主任医师",
            "intro": "擅长急腹症、阑尾炎与微创外科快速处置。",
            "specialty": "右下腹痛、急腹症",
            "schedule": "09:30-12:00",
            "slots": 2,
            "fee": 65,
            "location": "门诊楼 7 层急腹症单元",
        }
    ],
    "急诊科": [
        {
            "id": "er-1",
            "name": "急诊值班团队",
            "title": "24 小时接诊",
            "intro": "危重症快速评估与绿色通道处置。",
            "specialty": "胸痛、呼吸困难、意识异常",
            "schedule": "00:00-23:59",
            "slots": 999,
            "fee": 0,
            "location": "急诊楼 1 层",
        }
    ],
    "全科医学科": [
        {
            "id": "gp-1",
            "name": "王乐丞",
            "title": "主治医师",
            "intro": "擅长初诊分诊、慢病管理与症状初筛。",
            "specialty": "初诊评估、综合分诊",
            "schedule": "09:00-17:00",
            "slots": 8,
            "fee": 28,
            "location": "门诊楼 1 层全科中心",
        }
    ],
    "耳鼻喉科": [
        {
            "id": "ent-1",
            "name": "江临",
            "title": "副主任医师",
            "intro": "擅长咽痛、急慢性鼻炎及耳鸣门诊评估。",
            "specialty": "咽痛、鼻塞、耳鸣",
            "schedule": "09:00-12:00",
            "slots": 7,
            "fee": 40,
            "location": "门诊楼 3 层 C 区",
        },
        {
            "id": "ent-2",
            "name": "叶知夏",
            "title": "主治医师",
            "intro": "擅长扁桃体炎、咽喉不适和过敏性鼻炎管理。",
            "specialty": "扁桃体炎、鼻炎",
            "schedule": "14:00-17:00",
            "slots": 8,
            "fee": 26,
            "location": "门诊楼 3 层 C 区",
        },
    ],
    "骨科": [
        {
            "id": "ortho-1",
            "name": "陆沉",
            "title": "主任医师",
            "intro": "擅长关节疼痛、创伤后疼痛与运动损伤处理。",
            "specialty": "关节疼痛、运动损伤",
            "schedule": "09:30-12:00",
            "slots": 5,
            "fee": 60,
            "location": "门诊楼 6 层 A 区",
        },
        {
            "id": "ortho-2",
            "name": "何砚舟",
            "title": "主治医师",
            "intro": "擅长扭伤拉伤、颈肩腰腿痛与骨科随访。",
            "specialty": "扭伤、腰腿痛",
            "schedule": "13:30-17:00",
            "slots": 9,
            "fee": 30,
            "location": "门诊楼 6 层 A 区",
        },
    ],
    "内分泌科": [
        {
            "id": "endo-1",
            "name": "沈青禾",
            "title": "副主任医师",
            "intro": "擅长糖尿病、甲状腺结节与代谢综合征评估。",
            "specialty": "糖尿病、甲状腺",
            "schedule": "08:30-11:30",
            "slots": 6,
            "fee": 48,
            "location": "门诊楼 5 层 B 区",
        },
        {
            "id": "endo-2",
            "name": "许星然",
            "title": "主治医师",
            "intro": "擅长血糖管理和肥胖相关代谢咨询。",
            "specialty": "血糖管理、代谢咨询",
            "schedule": "14:00-17:30",
            "slots": 7,
            "fee": 32,
            "location": "门诊楼 5 层 B 区",
        },
    ],
    "妇科": [
        {
            "id": "gyn-1",
            "name": "苏禾",
            "title": "主任医师",
            "intro": "擅长月经异常、盆腔痛与常见妇科炎症诊疗。",
            "specialty": "月经异常、下腹痛",
            "schedule": "09:00-12:00",
            "slots": 5,
            "fee": 58,
            "location": "门诊楼 2 层 C 区",
        },
        {
            "id": "gyn-2",
            "name": "程晚",
            "title": "主治医师",
            "intro": "擅长白带异常、妇科感染和复诊随访。",
            "specialty": "妇科感染、复诊",
            "schedule": "13:30-16:30",
            "slots": 8,
            "fee": 28,
            "location": "门诊楼 2 层 C 区",
        },
    ],
    "儿科": [
        {
            "id": "ped-1",
            "name": "陶然",
            "title": "副主任医师",
            "intro": "擅长儿童发热、呼吸道感染与过敏评估。",
            "specialty": "儿童发热、咳嗽",
            "schedule": "09:00-12:00",
            "slots": 10,
            "fee": 35,
            "location": "儿科门诊楼 2 层",
        },
        {
            "id": "ped-2",
            "name": "邵知予",
            "title": "主治医师",
            "intro": "擅长儿童腹泻、呕吐和急性胃肠炎评估。",
            "specialty": "儿童腹泻、呕吐",
            "schedule": "14:00-17:00",
            "slots": 9,
            "fee": 24,
            "location": "儿科门诊楼 2 层",
        },
    ],
}

SUMMARY_DEFAULTS: Dict[str, object] = {
    "chiefComplaint": "待补充",
    "duration": "待补充",
    "accompanyingSymptoms": [],
    "redFlags": [],
    "recommendedDepartment": "待判断",
    "departmentReason": "根据现有症状综合判断。",
    "triagePriority": "待判断",
    "missingInformation": [],
    "nextQuestion": "",
    "doctorSummary": "患者信息尚未完善，等待对话开始。",
    "pastHistory": [],
    "allergyHistory": "待补充",
    "medicationHistory": "待补充",
    "consistencyAlerts": [],
    "imageFindings": "未提供影像",
    "departmentProfile": {},
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
        raise RuntimeError(f"尚未配置{config['label']}接口，请检查 .env 中的 {prefix}_API_KEY。")

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


def normalize_model_summary(summary: Dict[str, object], has_image: bool, provider_settings: Dict[str, object]) -> Dict[str, object]:
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


def call_model_api(provider: str, messages: List[Dict[str, object]]) -> Dict[str, object]:
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

    normalized = normalize_model_summary(summary, contains_uploaded_image(messages), provider_settings)
    normalized["_model"] = provider_settings["model_name"]
    normalized["_provider"] = provider
    normalized["_provider_label"] = provider_settings["label"]
    return normalized


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


def list_department_doctors(department: str) -> List[Dict[str, object]]:
    return DOCTOR_SCHEDULES.get(department, [])


def list_departments() -> List[Dict[str, object]]:
    names = sorted(set(DEPARTMENT_DETAILS.keys()) | set(DOCTOR_SCHEDULES.keys()))
    departments: List[Dict[str, object]] = []
    for name in names:
        profile = build_department_profile(name)
        departments.append(
            {
                "name": name,
                "location": profile["location"],
                "waitTime": profile["waitTime"],
                "overview": profile["overview"],
                "doctorCount": len(DOCTOR_SCHEDULES.get(name, [])),
            }
        )
    return departments


def format_list(items: object, empty_text: str) -> str:
    if isinstance(items, list) and items:
        return "、".join(str(item) for item in items)
    if isinstance(items, str) and items.strip():
        return items.strip()
    return empty_text


def build_summary_lines(summary: Dict[str, object]) -> List[str]:
    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return [
        "门诊预问诊单",
        f"导出时间：{exported_at}",
        "",
        "【结构化病历摘要】",
        f"主诉：{summary.get('chiefComplaint') or '待补充'}",
        f"症状持续时间：{summary.get('duration') or '待补充'}",
        f"伴随症状：{format_list(summary.get('accompanyingSymptoms'), '待补充')}",
        f"红旗征象：{format_list(summary.get('redFlags'), '暂未识别')}",
        f"影像/检查所见：{summary.get('imageFindings') or '未提供影像'}",
        f"信息一致性提醒：{format_list(summary.get('consistencyAlerts'), '暂无')}",
        f"既往史：{format_list(summary.get('pastHistory'), '待补充')}",
        f"过敏史：{summary.get('allergyHistory') or '待补充'}",
        f"近期用药史：{summary.get('medicationHistory') or '待补充'}",
        f"推荐科室：{summary.get('recommendedDepartment') or '待判断'}",
        f"科室推荐原因：{summary.get('departmentReason') or '待补充'}",
        f"就诊优先级：{summary.get('triagePriority') or '待判断'}",
        f"仍待补充信息：{format_list(summary.get('missingInformation'), '无')}",
        "",
        "【医生端摘要】",
        str(summary.get("doctorSummary") or "患者信息尚未完善，等待对话开始。"),
    ]


def generate_summary_pdf(summary: Dict[str, object]) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PDF 依赖未安装，请先执行 pip install -r requirements.txt。") from exc

    buffer = io.BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin_x = 44
    top = height - 52
    bottom = 54
    available_width = width - margin_x * 2
    cursor_y = top

    def ensure_page(required_height: float) -> None:
        nonlocal cursor_y
        if cursor_y - required_height < bottom:
            pdf.showPage()
            pdf.setTitle("门诊预问诊单")
            cursor_y = top

    def draw_text_line(text: str, font_name: str, font_size: int, line_gap: int) -> None:
        nonlocal cursor_y
        lines = simpleSplit(text, font_name, font_size, available_width) or [""]
        ensure_page(len(lines) * line_gap)
        pdf.setFont(font_name, font_size)
        for line in lines:
            pdf.drawString(margin_x, cursor_y, line)
            cursor_y -= line_gap

    pdf.setTitle("门诊预问诊单")
    draw_text_line("门诊预问诊单", "STSong-Light", 18, 24)
    draw_text_line("课程演示版 - 仅用于预问诊摘要与模拟挂号展示", "STSong-Light", 9, 16)
    cursor_y -= 6

    for line in build_summary_lines(summary)[1:]:
        if not line:
            cursor_y -= 8
            continue
        font_size = 12 if line.startswith("【") else 11
        line_gap = 18 if font_size == 12 else 17
        draw_text_line(line, "STSong-Light", font_size, line_gap)

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


@app.route("/")
def index():
    return redirect(url_for("patient_view"))


@app.get("/combined")
def combined_view():
    return render_template("index.html")


@app.get("/patient")
def patient_view():
    return render_template("patient.html")


@app.get("/doctor")
def doctor_view():
    return render_template("doctor.html")


@app.get("/api/sessions/<session_id>/stream")
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
                    # Keep the connection alive for proxies.
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


@app.post("/api/sessions/<session_id>/reset")
def api_session_reset(session_id: str):
    session_id = normalize_session_id(session_id)
    payload = build_session_payload(session_id)

    with SESSION_LOCK:
        SESSION_STATES[session_id] = payload

    publish_session_event(session_id, "reset", payload)
    return jsonify({"success": True, **payload})


@app.post("/api/chat")
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
            summary = call_model_api(provider, messages)
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


@app.get("/api/departments/<department>/doctors")
def api_department_doctors(department: str):
    doctors = list_department_doctors(department)
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


@app.get("/api/departments")
def api_departments():
    return jsonify({"departments": list_departments()})


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
        if doctor.get("id") != doctor_id:
            continue
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


@app.post("/api/export/pdf")
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True, threaded=True)
