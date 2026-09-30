import requests
from flask import Blueprint, abort, current_app, flash, render_template

blueprint = Blueprint("assessment", __name__, url_prefix="/assessment")

FUNCTIONS = ["GOVERN", "MAP", "MEASURE", "MANAGE"]


@blueprint.route("/<llm_id>", methods=["GET"])
def detail(llm_id: str):
    api_url = current_app.config.get("API_URL", "http://127.0.0.1:8000")

    try:
        llm_res = requests.get(f"{api_url}/api/llms/{llm_id}", timeout=3)
    except requests.exceptions.RequestException:
        abort(502, "ติดต่อ Matini API ไม่ได้ — ตรวจสอบว่า API service กำลังรันอยู่")
    if llm_res.status_code != 200:
        abort(404)
    llm = llm_res.json()

    # Active LLMs feed both dropdowns: the assessed AI (subject) and the judge.
    llms = []
    try:
        llms_res = requests.get(f"{api_url}/api/llms", timeout=3)
        if llms_res.status_code == 200:
            llms = llms_res.json()["llms"]
    except requests.exceptions.RequestException:
        flash("ดึงรายการ LLM จาก API ไม่ได้", "error")
    # The subject stays selectable even if it has been disabled in Admin.
    subject_options = llms if any(l["id"] == llm["id"] for l in llms) else [llm] + llms

    criteria = []
    try:
        criteria_res = requests.get(f"{api_url}/api/assessment/criteria", timeout=3)
        if criteria_res.status_code == 200:
            criteria = criteria_res.json()
    except requests.exceptions.RequestException:
        flash("ดึงรายการเกณฑ์ประเมินจาก API ไม่ได้", "error")

    report = None
    try:
        report_res = requests.get(f"{api_url}/api/assessment/{llm_id}", timeout=3)
        if report_res.status_code == 200:
            report = report_res.json()
    except requests.exceptions.RequestException:
        pass

    grouped_criteria = {fn: [c for c in criteria if c["nist_function"] == fn] for fn in FUNCTIONS}
    results_by_id = {r["criterion"]["id"]: r for r in report["criteria_results"]} if report else {}

    return render_template(
        "assessment/detail.html",
        llm=llm,
        subject_options=subject_options,
        judge_options=llms,
        functions=FUNCTIONS,
        grouped_criteria=grouped_criteria,
        report=report,
        results_by_id=results_by_id,
    )
