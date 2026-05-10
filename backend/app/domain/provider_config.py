from typing import Dict, List

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

SYSTEM_PROMPT = """你是一个具备视觉能力的门诊预问诊助手。你的任务不是给出最终诊断，而是：
1. 分析患者对话和上传的图片（如皮疹、化验单等），提取结构化病历摘要。
2. 识别红旗征象并给出分诊优先级。
3. 推荐就诊科室。
4. 继续提出下一轮最关键的追问。

请务必以 JSON 返回，且字段严格为：
chiefComplaint, duration, accompanyingSymptoms, redFlags, recommendedDepartment, departmentReason, triagePriority, missingInformation, nextQuestion, doctorSummary, pastHistory, allergyHistory, medicationHistory, consistencyAlerts, imageFindings

约束：
- imageFindings: 对上传图片的客观描述（如\"见红色斑丘疹\"），如果没有图片则返回\"未提供影像\"。
- triagePriority 只能是：普通 / 尽快 / 紧急
- 不要给出确定性诊断
- 输出内容必须是合法 JSON，不要使用 Markdown 代码块
"""

SUMMARY_DEFAULTS: Dict[str, object] = {
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
