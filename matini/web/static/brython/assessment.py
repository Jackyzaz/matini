from browser import bind, document, window

from common import error_detail, request, show_toast

POLL_MS = 1500

form = document["assessment_form"]
llm_id = form.attrs["data-llm-id"]
run_btn = document["run_btn"]
card = document["progress_card"]
job_key = "matini.assessment_job." + llm_id
subject_select = document["subject_select"]
judge_select = document["judge_select"]
warning = document["same_model_warning"]
JUDGE_KEY = "matini.judge_llm_id"
ASSESSOR_KEY = "matini.assessor_name"
MANUAL = "manual"  # the judge_select value for a human assessor
manual_fields = document["manual_fields"]
assessor_input = document["assessor_name"]
probes_checkbox = document.select_one("input[name=run_probes]")


def ls_get(key):
    try:
        return window.localStorage.getItem(key)
    except Exception:
        return None


def ls_set(key, value):
    try:
        if value is None:
            window.localStorage.removeItem(key)
        else:
            window.localStorage.setItem(key, value)
    except Exception:
        pass


def set_running(running):
    run_btn.disabled = running
    if running:
        card.classList.remove("hidden")
    else:
        card.classList.add("hidden")


def render_progress(job):
    total = job["total"] or 1
    percent = int(job["step"] * 100 / total)
    document["progress_bar"].value = percent
    document["progress_percent"].text = f"{percent}%"
    document["progress_step"].text = f"{job['step']}/{job['total']}"
    document["progress_label"].text = job["label"]


def poll(job_id, manual=False):
    def ok(job):
        render_progress(job)
        if job["status"] == "running":
            window.setTimeout(lambda: poll(job_id, manual), POLL_MS)
        elif job["status"] == "done":
            ls_set(job_key, None)
            if manual:
                window.location.href = f"/assessment/{llm_id}/manual/{job['report_id']}"
            else:
                window.location.reload()
        else:
            ls_set(job_key, None)
            set_running(False)
            show_toast("การประเมินล้มเหลว: " + (job["error"] or "unknown"), True)

    def failed(req):
        if req.status == 404:
            # API restarted: the job is gone, so stop waiting for it.
            ls_set(job_key, None)
            set_running(False)
            show_toast("ไม่พบงานประเมิน (API อาจถูกรีสตาร์ท) — กรุณารันใหม่", True)
        else:
            # Transient network error: keep trying.
            window.setTimeout(lambda: poll(job_id, manual), POLL_MS * 2)

    request("get", "/api/assessment/jobs/" + job_id, ok, on_error=failed)


def is_same_model(subject_option, judge_option):
    """Same registered LLM, or the same Ollama model tag on the same endpoint."""
    return subject_option.value == judge_option.value or (
        subject_option.attrs["data-model-name"] == judge_option.attrs["data-model-name"]
        and subject_option.attrs["data-base-url"] == judge_option.attrs["data-base-url"]
    )


def is_manual():
    return judge_select.value == MANUAL


def update_warning(ev=None):
    if judge_select.options.length == 0 or is_manual():
        warning.classList.add("hidden")
        return
    subject_option = subject_select.options[subject_select.selectedIndex]
    judge_option = judge_select.options[judge_select.selectedIndex]
    if is_same_model(subject_option, judge_option):
        warning.classList.remove("hidden")
    else:
        warning.classList.add("hidden")


def choose_default_judge():
    """Last used judge if still available, else the first LLM that isn't the subject, else the subject (or 'manual' if no LLM)."""
    values = [o.value for o in judge_select.options]
    saved = ls_get(JUDGE_KEY)
    if saved in values:
        judge_select.value = saved
        return
    others = [v for v in values if v not in (llm_id, MANUAL)]
    if others:
        judge_select.value = others[0]


def update_mode():
    """A human assessor needs the MEASURE replies to score, so probes are forced on and the name is required."""
    manual = is_manual()
    if manual:
        manual_fields.classList.remove("hidden")
    else:
        manual_fields.classList.add("hidden")
    if manual:
        probes_checkbox.checked = True
    probes_checkbox.disabled = manual
    document["run_btn_text"].text = "เริ่มประเมินโดยมนุษย์" if manual else "Run NIST AI RMF Assessment"
    update_warning()


def on_judge_change(ev):
    ls_set(JUDGE_KEY, judge_select.value)
    update_mode()


def on_subject_change(ev):
    window.location.href = "/assessment/" + subject_select.value


def start(ev):
    ev.preventDefault()
    if not judge_select.value:
        show_toast("กรุณาเลือกผู้ตัดสิน", True)
        return
    manual = is_manual()
    if manual:
        assessor = assessor_input.value.strip()
        if not assessor:
            show_toast("กรุณากรอกชื่อผู้ประเมิน", True)
            assessor_input.focus()
            return
        ls_set(ASSESSOR_KEY, assessor)
        url = f"/api/assessment/{llm_id}/manual"
        body = {"assessor_name": assessor}
    else:
        url = f"/api/assessment/{llm_id}/run"
        body = {"judge_llm_id": judge_select.value, "run_probes": probes_checkbox.checked}
    set_running(True)
    render_progress({"step": 0, "total": 1, "label": "เริ่มการประเมิน…"})
    window.scrollTo(0, 0)

    def started(job):
        ls_set(job_key, ("manual:" if manual else "") + job["job_id"])
        poll(job["job_id"], manual)

    def failed(req):
        set_running(False)
        show_toast(error_detail(req), True)

    request("post", url, started, data=body, on_error=failed)


def on_history_change(ev):
    window.location.href = f"/assessment/{llm_id}?report=" + document["history_select"].value


def discard_draft(ev):
    if not window.confirm("ทิ้งร่างการประเมินนี้? คะแนนที่ให้ไว้จะหายไป"):
        return
    report_id = document["draft_card"].attrs["data-report-id"]
    request("delete", "/api/assessment/reports/delete/" + report_id, lambda _: window.location.assign(f"/assessment/{llm_id}"))


form.bind("submit", start)
if "history_select" in document:
    document["history_select"].bind("change", on_history_change)
if "discard_draft" in document:
    document["discard_draft"].bind("click", discard_draft)
subject_select.bind("change", on_subject_change)
judge_select.bind("change", on_judge_change)
choose_default_judge()
assessor_input.value = ls_get(ASSESSOR_KEY) or ""
update_mode()

# Resume the progress bar if the page was reloaded/reopened while a run was in flight.
saved_job = ls_get(job_key)
if saved_job:
    set_running(True)
    poll(saved_job.replace("manual:", ""), saved_job.startswith("manual:"))
