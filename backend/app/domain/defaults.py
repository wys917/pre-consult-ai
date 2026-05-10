from typing import Dict

DEFAULT_SESSION_ID = "default"


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
        "visitPreparation": [],
        "selfCareAdvice": [],
        "followUpPlan": [],
        "workflowStage": "collecting",
        "workflowStageLabel": "信息采集中",
        "handoffBanner": {},
        "workflowTimeline": [],
        "bookingStatus": "pending",
        "bookingRecord": {},
        "doctorHandoff": {},
        "patientNextSteps": [],
        "confidenceScore": 0.0,
        "reviewReason": "",
        "riskSource": "rule",
        "needsManualReview": False,
        "lifecycleState": "intake_started",
    }
