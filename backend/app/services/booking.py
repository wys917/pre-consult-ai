import io
import uuid
from datetime import datetime
from typing import Dict, List


def list_department_doctors(department: str, doctor_schedules: Dict[str, List[Dict[str, object]]]) -> List[Dict[str, object]]:
    return doctor_schedules.get(department, [])


def list_departments(
    department_details: Dict[str, Dict[str, str]],
    doctor_schedules: Dict[str, List[Dict[str, object]]],
    *,
    build_department_profile,
) -> List[Dict[str, object]]:
    names = sorted(set(department_details.keys()) | set(doctor_schedules.keys()))
    departments: List[Dict[str, object]] = []
    for name in names:
        profile = build_department_profile(name)
        departments.append(
            {
                "name": name,
                "location": profile["location"],
                "waitTime": profile["waitTime"],
                "overview": profile["overview"],
                "doctorCount": len(doctor_schedules.get(name, [])),
            }
        )
    return departments


def book_appointment(
    *,
    department: str,
    doctor_id: str,
    patient_name: str,
    doctor_schedules: Dict[str, List[Dict[str, object]]],
) -> Dict[str, object]:
    doctors = list_department_doctors(department, doctor_schedules)
    for doctor in doctors:
        if doctor.get("id") != doctor_id:
            continue
        if int(doctor.get("slots", 0)) <= 0:
            raise ValueError("该医生号源已满，请选择其他医生")
        if doctor_id != "er-1":
            doctor["slots"] = int(doctor["slots"]) - 1
        return {
            "success": True,
            "appointmentId": f"APT-{uuid.uuid4().hex[:8].upper()}",
            "message": f"{patient_name} 挂号成功，已预约 {doctor['name']}（{doctor['title']}）。",
            "department": department,
            "doctor": doctor,
        }
    raise LookupError("未找到对应医生")


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
