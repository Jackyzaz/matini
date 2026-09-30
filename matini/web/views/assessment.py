import requests
from flask import Blueprint, current_app, abort, flash, redirect, render_template, request, url_for

blueprint = Blueprint("assessment", __name__, url_prefix="/model")


@blueprint.route("/<model_id>/assessment", methods=["GET"])
def detail(model_id: str):
    api_url = current_app.config.get("API_URL", "http://127.0.0.1:8000")

    model_res = requests.get(f"{api_url}/api/models/{model_id}", timeout=3)
    if model_res.status_code != 200:
        abort(404)
    model_data = model_res.json()

    criteria = []
    try:
        criteria_res = requests.get(f"{api_url}/api/assessment/criteria", timeout=3)
        if criteria_res.status_code == 200:
            criteria = criteria_res.json()
    except requests.exceptions.RequestException:
        flash("ติดต่อ Matini API ไม่ได้ (สำหรับดึงรายการเกณฑ์ประเมิน) — ตรวจสอบว่า API service กำลังรันอยู่", "error")

    report = None
    try:
        report_res = requests.get(f"{api_url}/api/assessment/{model_id}", timeout=3)
        if report_res.status_code == 200:
            report = report_res.json()
    except requests.exceptions.RequestException:
        pass

    functions = ["GOVERN", "MAP", "MEASURE", "MANAGE"]
    grouped_criteria = {fn: [c for c in criteria if c["nist_function"] == fn] for fn in functions}

    results_by_id = {}
    if report:
        results_by_id = {r["criterion"]["id"]: r for r in report["criteria_results"]}

    return render_template(
        "assessment/detail.html",
        model=model_data,
        functions=functions,
        grouped_criteria=grouped_criteria,
        report=report,
        results_by_id=results_by_id,
        api_url=api_url,
    )


@blueprint.route("/<model_id>/assessment/run", methods=["POST"])
def run(model_id: str):
    api_url = current_app.config.get("API_URL", "http://127.0.0.1:8000")

    try:
        criteria_res = requests.get(f"{api_url}/api/assessment/criteria", timeout=3)
        criteria = criteria_res.json() if criteria_res.status_code == 200 else []
    except requests.exceptions.RequestException:
        flash("ติดต่อ Matini API ไม่ได้ — ไม่สามารถเริ่มการประเมินได้", "error")
        return redirect(url_for("assessment.detail", model_id=model_id))

    payload = {
        "system_context": request.form.get("system_context", ""),
        "run_probes": request.form.get("run_probes") == "on",
        "criteria_inputs": [
            {"criterion_id": c["id"], "evidence_notes": request.form.get(f"evidence__{c['id']}", "")}
            for c in criteria
        ],
    }

    try:
        # Local LLM inference (subject probes + judge scoring, up to ~12 items) can
        # take a while on modest hardware — keep this timeout generous.
        res = requests.post(f"{api_url}/api/assessment/{model_id}/run", json=payload, timeout=900)
        if res.status_code == 200:
            flash("ประเมินสำเร็จ", "success")
        else:
            try:
                detail_msg = res.json().get("detail", res.text)
            except ValueError:
                detail_msg = res.text
            flash(f"ประเมินไม่สำเร็จ: {detail_msg}", "error")
    except requests.exceptions.RequestException as exc:
        flash(f"ติดต่อ API ไม่ได้ระหว่างรันการประเมิน: {exc}", "error")

    return redirect(url_for("assessment.detail", model_id=model_id))
