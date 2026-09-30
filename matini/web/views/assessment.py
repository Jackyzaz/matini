import requests
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

blueprint = Blueprint("assessment", __name__, url_prefix="/assessment")

FUNCTIONS = ["GOVERN", "MAP", "MEASURE", "MANAGE"]

STATUS_LABELS = {
    "implemented": "ดำเนินการแล้ว",
    "partial": "ดำเนินการบางส่วน",
    "not_implemented": "ยังไม่ได้ดำเนินการ",
    "unknown": "ไม่ระบุ",
}
KIND_LABELS = {"document": "เอกสาร", "link": "ลิงก์", "text": "ข้อความ"}


def _is_filled(evidence: dict) -> bool:
    return evidence.get("status", "unknown") != "unknown" or bool(evidence.get("notes", "").strip()) or bool(evidence.get("items"))


def summarize_profile(profile: dict, grouped_criteria: dict) -> dict:
    """How complete the LLM's assessment profile is, per NIST function (drives the card on the page)."""
    declared = profile.get("criteria", {})
    functions = []
    for fn in FUNCTIONS:
        ids = [c["id"] for c in grouped_criteria.get(fn, [])]
        functions.append({"name": fn, "filled": sum(1 for i in ids if i in declared and _is_filled(declared[i])), "total": len(ids)})
    context_filled = sum(1 for v in profile.get("system_context", {}).values() if str(v).strip())
    return {
        "functions": functions,
        "context_filled": context_filled,
        "is_empty": context_filled == 0 and all(f["filled"] == 0 for f in functions),
        "updated_date": profile.get("updated_date"),
    }


def history_options(history: list, selected_id: str) -> list:
    """Rows for the history dropdown: who judged, when, and the score (or how far a draft has got)."""
    rows = []
    for item in history:
        human = item.get("judge_type") == "human"
        who = f"มนุษย์: {item.get('assessor_name') or '-'}" if human else f"AI: {item.get('judge_llm_name') or item.get('judge_model') or '-'}"
        when = str(item["created_date"])[:16].replace("T", " ")
        if item.get("status") == "draft":
            scored = sum(1 for r in item["criteria_results"] if r.get("score") is not None)
            detail = f"ร่าง {scored}/{len(item['criteria_results'])}"
        else:
            detail = f"{item['overall_score']}/5" if item.get("overall_score") is not None else "—"
        rows.append({"id": item["id"], "label": f"{when} • {who} • {detail}", "selected": item["id"] == selected_id})
    return rows


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

    # Every report of this LLM (newest first, drafts included). ?report=<id> picks one; the default is the
    # newest finished report, because a draft has no result yet.
    history = []
    try:
        history_res = requests.get(f"{api_url}/api/assessment/{llm_id}/history", timeout=3)
        if history_res.status_code == 200:
            history = history_res.json()
    except requests.exceptions.RequestException:
        pass
    wanted = request.args.get("report")
    selected = next((h for h in history if h["id"] == wanted), None)
    if selected is None:
        selected = next((h for h in history if h.get("status", "completed") == "completed"), None)
    draft = selected if selected and selected.get("status") == "draft" else None
    report = selected if selected and not draft else None

    grouped_criteria = {fn: [c for c in criteria if c["nist_function"] == fn] for fn in FUNCTIONS}
    results_by_id = {r["criterion"]["id"]: r for r in report["criteria_results"]} if report else {}

    profile_summary = summarize_profile(llm.get("assessment_profile") or {}, grouped_criteria)

    return render_template(
        "assessment/detail.html",
        llm=llm,
        subject_options=subject_options,
        judge_options=llms,
        functions=FUNCTIONS,
        grouped_criteria=grouped_criteria,
        report=report,
        draft=draft,
        history=history_options(history, selected["id"] if selected else ""),
        results_by_id=results_by_id,
        profile_summary=profile_summary,
        status_labels=STATUS_LABELS,
        kind_labels=KIND_LABELS,
    )


@blueprint.route("/<llm_id>/manual/<report_id>", methods=["GET"])
def manual(llm_id: str, report_id: str):
    """Human assessment of one draft report: read the evidence / model replies, score each criterion."""
    api_url = current_app.config.get("API_URL", "http://127.0.0.1:8000")
    try:
        res = requests.get(f"{api_url}/api/assessment/reports/{report_id}", timeout=3)
    except requests.exceptions.RequestException:
        abort(502, "ติดต่อ Matini API ไม่ได้ — ตรวจสอบว่า API service กำลังรันอยู่")
    if res.status_code != 200:
        abort(404)
    report = res.json()
    if report["llm_id"] != llm_id or report.get("judge_type") != "human":
        abort(404)
    if report.get("status") == "completed":
        return redirect(url_for("assessment.detail", llm_id=llm_id, report=report_id))

    return render_template(
        "assessment/manual.html",
        report=report,
        functions=FUNCTIONS,
        status_labels=STATUS_LABELS,
        kind_labels=KIND_LABELS,
    )
