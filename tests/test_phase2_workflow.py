from backend.app.services.triage import analyze_conversation
from backend.app.services.workflow import (
    build_follow_up_plan,
    build_self_care_advice,
    build_visit_preparation,
    enrich_summary_workflow,
)


def test_build_visit_preparation_includes_department_and_history_context():
    summary = {
        "recommendedDepartment": "呼吸内科",
        "accompanyingSymptoms": ["发热", "咳嗽"],
        "pastHistory": ["高血压"],
        "redFlags": [],
        "imageFindings": "未提供影像",
    }

    result = build_visit_preparation(summary)

    assert any("呼吸内科" in item for item in result)
    assert any("既往病历" in item for item in result)
    assert any("体温记录" in item for item in result)


def test_build_self_care_advice_escalates_emergency_cases():
    result = build_self_care_advice({"triagePriority": "紧急", "accompanyingSymptoms": [], "redFlags": []})
    assert result == ["当前以尽快线下急诊处理为主，不建议自行观察或延迟就诊。"]


def test_build_follow_up_plan_prioritizes_missing_information_and_department():
    summary = {
        "missingInformation": ["年龄", "症状持续时间"],
        "triagePriority": "尽快",
        "recommendedDepartment": "消化内科",
    }

    result = build_follow_up_plan(summary)

    assert "年龄" in result[0]
    assert any("今天内尽快线下就诊" in item for item in result)
    assert any("消化内科" in item for item in result)


def test_enrich_summary_workflow_adds_phase2_fields():
    enriched = enrich_summary_workflow(
        {
            "recommendedDepartment": "全科医学科",
            "triagePriority": "普通",
            "missingInformation": [],
            "accompanyingSymptoms": [],
            "redFlags": [],
            "pastHistory": [],
            "imageFindings": "未提供影像",
        }
    )

    assert "visitPreparation" in enriched
    assert "selfCareAdvice" in enriched
    assert "followUpPlan" in enriched
    assert "workflowStage" in enriched
    assert "workflowStageLabel" in enriched
    assert "handoffBanner" in enriched
    assert "workflowTimeline" in enriched
    assert isinstance(enriched["visitPreparation"], list)


def test_enrich_summary_workflow_marks_collecting_stage_when_information_missing():
    enriched = enrich_summary_workflow(
        {
            "recommendedDepartment": "待判断",
            "triagePriority": "待判断",
            "missingInformation": ["年龄", "症状持续时间"],
            "nextQuestion": "请补充年龄和症状持续时间。",
            "accompanyingSymptoms": [],
            "redFlags": [],
            "pastHistory": [],
            "imageFindings": "未提供影像",
        }
    )

    assert enriched["workflowStage"] == "collecting"
    assert enriched["workflowStageLabel"] == "信息采集中"
    assert enriched["handoffBanner"]["title"] == "继续补充预问诊信息"
    assert enriched["workflowTimeline"][0]["status"] == "active"


def test_enrich_summary_workflow_marks_booking_stage_when_ready():
    enriched = enrich_summary_workflow(
        {
            "recommendedDepartment": "呼吸内科",
            "triagePriority": "尽快",
            "missingInformation": [],
            "accompanyingSymptoms": ["发热"],
            "redFlags": [],
            "pastHistory": [],
            "imageFindings": "未提供影像",
        }
    )

    assert enriched["workflowStage"] == "ready_for_booking"
    assert enriched["workflowStageLabel"] == "可进入挂号"
    assert "呼吸内科" in enriched["handoffBanner"]["title"]
    assert any(step["key"] == "booking" and step["status"] == "active" for step in enriched["workflowTimeline"])


def test_enrich_summary_workflow_marks_urgent_handoff():
    enriched = enrich_summary_workflow(
        {
            "recommendedDepartment": "急诊科",
            "triagePriority": "紧急",
            "missingInformation": [],
            "accompanyingSymptoms": ["胸痛"],
            "redFlags": ["持续胸痛"],
            "pastHistory": [],
            "imageFindings": "未提供影像",
        }
    )

    assert enriched["workflowStage"] == "urgent_handoff"
    assert enriched["handoffBanner"]["level"] == "danger"
    assert enriched["handoffBanner"]["title"] == "立即急诊分流"
    assert any(step["key"] == "booking" and step["status"] == "completed" for step in enriched["workflowTimeline"])


def test_analyze_conversation_returns_phase2_workflow_fields():
    summary = analyze_conversation(
        [{"role": "user", "content": "我45岁，发烧咳嗽三天，还有高血压。"}]
    )

    assert "visitPreparation" in summary
    assert "selfCareAdvice" in summary
    assert "followUpPlan" in summary
    assert isinstance(summary["visitPreparation"], list)
    assert isinstance(summary["selfCareAdvice"], list)
    assert isinstance(summary["followUpPlan"], list)
