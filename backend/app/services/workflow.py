from typing import Dict, List


FOLLOW_UP_URGENCY_MAP = {
    "紧急": "建议立即前往急诊或呼叫 120，不建议继续等待线上问诊。",
    "尽快": "建议今天内尽快线下就诊，优先完成面诊和必要检查。",
    "普通": "可先按建议补充信息，并根据号源安排尽快就诊。",
    "待判断": "建议继续补充关键信息后再决定就诊时机。",
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


def enrich_summary_workflow(summary: Dict[str, object]) -> Dict[str, object]:
    enriched = dict(summary)
    enriched["visitPreparation"] = build_visit_preparation(enriched)
    enriched["selfCareAdvice"] = build_self_care_advice(enriched)
    enriched["followUpPlan"] = build_follow_up_plan(enriched)
    return enriched
