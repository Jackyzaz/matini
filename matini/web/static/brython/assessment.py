from browser import bind, document, window

from common import error_detail, request, show_toast

POLL_MS = 1500

form = document["assessment_form"]
llm_id = form.attrs["data-llm-id"]
run_btn = document["run_btn"]
card = document["progress_card"]
job_key = "matini.assessment_job." + llm_id


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


def poll(job_id):
    def ok(job):
        render_progress(job)
        if job["status"] == "running":
            window.setTimeout(lambda: poll(job_id), POLL_MS)
        elif job["status"] == "done":
            ls_set(job_key, None)
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
            window.setTimeout(lambda: poll(job_id), POLL_MS * 2)

    request("get", "/api/assessment/jobs/" + job_id, ok, on_error=failed)


def start(ev):
    ev.preventDefault()
    body = {
        "system_context": document.select_one("textarea[name=system_context]").value,
        "run_probes": document.select_one("input[name=run_probes]").checked,
        "criteria_inputs": [
            {"criterion_id": ta.attrs["name"][len("evidence__"):], "evidence_notes": ta.value}
            for ta in document.select("textarea[name^=evidence__]")
        ],
    }
    set_running(True)
    render_progress({"step": 0, "total": 1, "label": "เริ่มการประเมิน…"})
    window.scrollTo(0, 0)

    def started(job):
        ls_set(job_key, job["job_id"])
        poll(job["job_id"])

    def failed(req):
        set_running(False)
        show_toast(error_detail(req), True)

    request("post", f"/api/assessment/{llm_id}/run", started, data=body, on_error=failed)


form.bind("submit", start)

# Resume the progress bar if the page was reloaded/reopened while a run was in flight.
saved_job = ls_get(job_key)
if saved_job:
    set_running(True)
    poll(saved_job)
