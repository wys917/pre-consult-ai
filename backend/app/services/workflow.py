from typing import Dict, List


FOLLOW_UP_URGENCY_MAP = {
    "紧急": "建议立即前往急诊或呼叫 120，不建议继续等待线上问诊。",
    "尽快": "建议今天内尽快线下就诊，优先完成面诊和必要检查。",
    "普通": "可先按建议补充信息，并根据号源安排尽快就诊。",
    "待判断": "建议继续补充关键信息后再决定就诊时机。",
}


HIGH_RISK_SYMPTOMS = {"胸痛", "呼吸困难", "意识异常", "抽搐", "便血", "黑便", "呕血"}
URGENT_PRIORITIES = {"紧急", "尽快"}
LIFECYCLE_STATE_MAP = {
    "collecting": "intake_started",
    "ready_for_triage": "triage_ready",
    "ready_for_booking": "ready_for_booking",
    "urgent_handoff": "escalated_to_er",
    "booked": "booked",
}


STAGE_LABELS = {
    "collecting": "信息采集中",
    "ready_for_triage": "可进入分诊",
    "ready_for_booking": "可进入挂号",
    "urgent_handoff": "紧急转诊",
    "booked": "已完成挂号",
}


def build_visit_preparation(summary: Dict[str, object]) -> List[str]:
    preparations: List[str] = []
    department = str(summary.get("recommendedDepartment") or "").strip()
    symptoms = summary.get("accompanyingSymptoms") or []
    red_flags = summary.get("redFlags") or []
    past_history = summary.get("pastHistory") or []
    has_image = str(summary.get("imageFindings") or "") != "未提供影像"

    if department and department not in {"待判断", "待补充"}:
        preparations.append(f"挂号时优先选择{department}，并向分诊台说明主诉与当前优先级。")
    if past_history:
        preparations.append("携带既往病历、慢病随访记录或近期化验单，帮助医生快速了解基础病情况。")
    if has_image:
        preparations.append("保留已上传影像或检查资料原图，到院后可向医生出示完整版本。")
    if "发热" in symptoms:
        preparations.append("如有体温记录，请整理最高体温、起病时间和退热药使用情况。")
    if "胸痛" in symptoms or "心悸" in symptoms:
        preparations.append("记录发作时间、持续时长以及是否伴随活动后加重，便于心血管方向评估。")
    if "腹痛" in symptoms:
        preparations.append("就诊前尽量回忆腹痛部位、加重因素以及是否伴恶心、呕吐、腹泻。")
    if red_flags:
        preparations.append("若途中出现症状突然加重、意识异常或持续胸闷气短，应立即改走急诊流程。")

    if not preparations:
        preparations.append("建议提前整理主要症状、持续时间和既往病史，便于线下面诊时快速沟通。")

    return preparations[:4]


def build_self_care_advice(summary: Dict[str, object]) -> List[str]:
    advice: List[str] = []
    priority = str(summary.get("triagePriority") or "待判断")
    symptoms = summary.get("accompanyingSymptoms") or []
    red_flags = summary.get("redFlags") or []

    if priority == "紧急":
        return ["当前以尽快线下急诊处理为主，不建议自行观察或延迟就诊。"]

    if "发热" in symptoms:
        advice.append("发热期间注意补液与休息，持续高热或精神状态变差时尽快就医。")
    if "咳嗽" in symptoms or "咽痛" in symptoms:
        advice.append("如有呼吸道症状，建议佩戴口罩并减少与他人近距离接触。")
    if "腹痛" in symptoms:
        advice.append("腹痛明显时避免暴饮暴食；若疼痛持续加重，不要仅靠止痛药硬扛。")
    if "皮疹/瘙痒" in symptoms:
        advice.append("避免抓挠和继续接触可疑过敏源，必要时记录皮疹变化。")
    if red_flags:
        advice.append("一旦出现红旗征象加重，请停止居家观察并尽快线下就医。")

    if not advice:
        advice.append("在正式面诊前，可先休息并持续观察症状变化，如明显加重请提前就医。")

    return advice[:4]


def build_follow_up_plan(summary: Dict[str, object]) -> List[str]:
    missing = summary.get("missingInformation") or []
    priority = str(summary.get("triagePriority") or "待判断")
    plan: List[str] = []

    if missing:
        plan.append(f"下一轮先补充：{'、'.join(str(item) for item in missing[:3])}。")
    plan.append(FOLLOW_UP_URGENCY_MAP.get(priority, FOLLOW_UP_URGENCY_MAP["待判断"]))

    department = str(summary.get("recommendedDepartment") or "").strip()
    if department and department not in {"待判断", "待补充"}:
        plan.append(f"若号源允许，完成补充后可直接进入{department}挂号与接诊流程。")

    return plan[:3]


def build_patient_next_steps(summary: Dict[str, object], stage: str) -> List[str]:
    department = str(summary.get("recommendedDepartment") or "").strip()
    priority = str(summary.get("triagePriority") or "待判断")
    missing = [str(item) for item in (summary.get("missingInformation") or []) if str(item).strip()]
    booking = summary.get("bookingRecord") or {}

    if stage == "urgent_handoff":
        return [
            "请立即停止线上等待，优先前往急诊或呼叫 120。",
            "到院后直接说明当前症状与系统识别出的高风险信号。",
            "如途中出现持续胸闷、呼吸困难或意识变化，立即寻求现场帮助。",
        ]

    if stage == "booked":
        doctor_name = str(booking.get("doctorName") or "接诊医生")
        appointment_id = str(booking.get("appointmentId") or "预约单")
        return [
            f"已完成挂号：{appointment_id}，请按预约时间前往{department or '对应科室'}。",
            f"到院时向 {doctor_name} 出示当前预问诊摘要与既往资料。",
            "若症状在候诊前明显加重，请不要等待叫号，改走急诊分流。",
        ]

    if stage == "collecting":
        steps = []
        if missing:
            steps.append(f"先补充关键信息：{'、'.join(missing[:3])}。")
        steps.append("补充完成后，系统会自动更新推荐科室与下一步安排。")
        if priority == "尽快":
            steps.append("如线下就诊方便，建议今天内完成面诊，不必长时间等待线上补充。")
        return steps[:3]

    if stage == "ready_for_booking":
        return [
            f"当前已可进入{department or '推荐科室'}挂号流程。",
            "优先选择当日有号医生，并准备好既往病历、化验单或影像资料。",
            "挂号完成后，医生侧会直接看到结构化交接摘要。",
        ]

    return [
        "当前基础信息已较完整，可继续查看分诊建议。",
        "如仍有新增症状或风险信号，请及时补充给系统。",
        "确认科室后即可进入下一步挂号或接诊流程。",
    ]


def resolve_workflow_stage(summary: Dict[str, object]) -> str:
    priority = str(summary.get("triagePriority") or "待判断")
    missing = summary.get("missingInformation") or []
    department = str(summary.get("recommendedDepartment") or "").strip()
    booking_status = str(summary.get("bookingStatus") or "pending")

    if booking_status == "booked":
        return "booked"
    if priority == "紧急":
        return "urgent_handoff"
    if missing:
        return "collecting"
    if department and department not in {"待判断", "待补充"}:
        return "ready_for_booking"
    return "ready_for_triage"


def build_handoff_banner(summary: Dict[str, object], stage: str) -> Dict[str, str]:
    department = str(summary.get("recommendedDepartment") or "").strip() or "待判断"
    priority = str(summary.get("triagePriority") or "待判断")
    next_question = str(summary.get("nextQuestion") or "").strip()
    booking = summary.get("bookingRecord") or {}

    if stage == "booked":
        doctor_name = str(booking.get("doctorName") or "已预约医生")
        return {
            "level": "success",
            "title": "已完成挂号与交接",
            "message": f"已预约 {doctor_name}，建议患者按时到院，并将当前结构化摘要直接提供给接诊医生。",
        }
    if stage == "urgent_handoff":
        return {
            "level": "danger",
            "title": "立即急诊分流",
            "message": "系统识别到高风险信号，请停止继续线上补充，优先线下急诊处理。",
        }
    if stage == "collecting":
        return {
            "level": "info",
            "title": "继续补充预问诊信息",
            "message": next_question or "请先补齐缺失信息，再进入分诊与挂号流程。",
        }
    if stage == "ready_for_booking":
        return {
            "level": "success",
            "title": f"可进入{department}挂号",
            "message": f"当前优先级为{priority}，结构化摘要已可直接交接给医生侧或挂号台。",
        }
    return {
        "level": "info",
        "title": "可进入分诊评估",
        "message": "基础信息已较完整，可继续生成分诊建议或转给医生侧查看。",
    }


def build_workflow_timeline(summary: Dict[str, object], stage: str) -> List[Dict[str, object]]:
    missing = summary.get("missingInformation") or []
    department = str(summary.get("recommendedDepartment") or "").strip()
    booking = summary.get("bookingRecord") or {}

    collecting_done = not missing
    booking_ready = bool(department and department not in {"待判断", "待补充"}) and collecting_done and stage not in {"urgent_handoff", "booked"}
    booked = stage == "booked"

    return [
        {
            "key": "collect",
            "label": "患者信息采集",
            "status": "completed" if collecting_done else "active",
            "detail": "继续补充主诉、病程和关键信息" if not collecting_done else "基础信息已满足当前分诊需求",
        },
        {
            "key": "triage",
            "label": "AI 分诊整理",
            "status": "completed" if collecting_done else "pending",
            "detail": "输出推荐科室、优先级和风险提示",
        },
        {
            "key": "handoff",
            "label": "医生侧交接",
            "status": "completed" if booking_ready or stage in {"urgent_handoff", "booked"} else ("active" if collecting_done else "pending"),
            "detail": "医生端可查看结构化摘要与患者输入记录",
        },
        {
            "key": "booking",
            "label": "挂号 / 到院处理",
            "status": "completed" if stage in {"urgent_handoff", "booked"} else ("active" if booking_ready else "pending"),
            "detail": (
                f"已预约 {booking.get('department', '')} · {booking.get('doctorName', '')}".strip(" ·")
                if booked
                else "进入推荐科室挂号，或紧急情况下直接急诊"
            ),
        },
    ]


def build_doctor_handoff(summary: Dict[str, object]) -> Dict[str, object]:
    booking = summary.get("bookingRecord") or {}
    department = str(summary.get("recommendedDepartment") or "待判断")
    priority = str(summary.get("triagePriority") or "待判断")
    complaint = str(summary.get("chiefComplaint") or "待补充")
    duration = str(summary.get("duration") or "待补充")
    symptoms = "、".join(str(item) for item in (summary.get("accompanyingSymptoms") or [])) or "待补充"
    red_flags = "、".join(str(item) for item in (summary.get("redFlags") or [])) or "暂未识别"
    history = "、".join(str(item) for item in (summary.get("pastHistory") or [])) or "待补充"
    allergies = str(summary.get("allergyHistory") or "待补充")
    doctor_name = str(booking.get("doctorName") or "待分配")

    lines = [
        f"【接诊交接】推荐科室：{department}｜优先级：{priority}",
        f"主诉：{complaint}（{duration}）",
        f"伴随症状：{symptoms}",
        f"红旗征象：{red_flags}",
        f"既往史：{history}｜过敏史：{allergies}",
        f"接诊医生：{doctor_name}",
        f"医生摘要：{str(summary.get('doctorSummary') or '患者信息尚未完善，等待对话开始。')}",
    ]

    actions = [
        f"优先按 {department} 分诊接诊",
        "核对生命体征与主诉病程",
        "结合当前摘要继续补充体征、检查和用药信息",
    ]
    if booking.get("appointmentId"):
        actions.insert(0, f"已存在预约单号：{booking['appointmentId']}")

    return {
        "title": "医生接诊交接卡",
        "note": "\n".join(lines),
        "actions": actions[:4],
    }


def build_review_metadata(summary: Dict[str, object], stage: str) -> Dict[str, object]:
    missing = [str(item) for item in (summary.get("missingInformation") or []) if str(item).strip()]
    symptoms = {str(item).strip() for item in (summary.get("accompanyingSymptoms") or []) if str(item).strip()}
    red_flags = {str(item).strip() for item in (summary.get("redFlags") or []) if str(item).strip()}
    priority = str(summary.get("triagePriority") or "待判断")
    department = str(summary.get("recommendedDepartment") or "").strip()
    booking_status = str(summary.get("bookingStatus") or "pending")

    confidence = 0.85
    reasons: List[str] = []
    risk_source = "rule"
    needs_manual_review = False

    if len(missing) >= 3:
        needs_manual_review = True
        confidence = min(confidence, 0.35)
        reasons.append("关键字段缺失较多")

    if HIGH_RISK_SYMPTOMS.intersection(symptoms) and priority not in URGENT_PRIORITIES:
        needs_manual_review = True
        confidence = min(confidence, 0.45)
        reasons.append("高风险症状与当前分诊结果不一致")
        risk_source = "hybrid"

    if red_flags and priority == "普通":
        needs_manual_review = True
        confidence = min(confidence, 0.5)
        reasons.append("已识别红旗征象但优先级仍偏低")
        risk_source = "hybrid"

    if stage == "collecting":
        confidence = min(confidence, 0.65 if missing else 0.75)
    if stage == "urgent_handoff":
        confidence = max(confidence, 0.9)
    if booking_status == "booked" and department and department not in {"待判断", "待补充"}:
        confidence = max(confidence, 0.92)

    lifecycle_state = LIFECYCLE_STATE_MAP.get(stage, "intake_started")
    return {
        "confidenceScore": round(confidence, 2),
        "reviewReason": "；".join(reasons),
        "riskSource": risk_source,
        "needsManualReview": needs_manual_review,
        "lifecycleState": lifecycle_state,
    }


def enrich_summary_workflow(summary: Dict[str, object]) -> Dict[str, object]:
    enriched = dict(summary)
    enriched["visitPreparation"] = build_visit_preparation(enriched)
    enriched["selfCareAdvice"] = build_self_care_advice(enriched)
    enriched["followUpPlan"] = build_follow_up_plan(enriched)

    stage = resolve_workflow_stage(enriched)
    enriched["workflowStage"] = stage
    enriched["workflowStageLabel"] = STAGE_LABELS.get(stage, STAGE_LABELS["collecting"])
    enriched["handoffBanner"] = build_handoff_banner(enriched, stage)
    enriched["workflowTimeline"] = build_workflow_timeline(enriched, stage)
    enriched["doctorHandoff"] = build_doctor_handoff(enriched)
    enriched["patientNextSteps"] = build_patient_next_steps(enriched, stage)
    enriched.update(build_review_metadata(enriched, stage))
    return enriched
