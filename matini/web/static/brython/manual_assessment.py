"""Human assessment page: read the evidence / the model's replies, score each criterion against its rubric.

The page is rendered by Flask with one <section> per criterion; this script shows the current one, saves
scores one at a time (the report is a draft on the server until "ส่งผลการประเมิน"), and owns the parts that
change at runtime: the MEASURE probe cards and the document viewer.
`json` is imported inside functions on purpose: see the "Brython gotchas" in CLAUDE.md.
"""
from browser import bind, document, html, window

from common import api_url, error_detail, request, show_toast

PROBE_TIMEOUT_S = 600  # a local model can take minutes to answer

root = document["manual_app"]
llm_id = root.attrs["data-llm-id"]
report_id = root.attrs["data-report-id"]

panels = document.select("section[data-criterion-id]")
steps = document.select("button[data-step]")
complete_btn = document["complete_btn"]

state = {
    "index": 0,
    "results": {},  # criterion id -> CriterionResult (probes, score, rationale)
    "saved": {},  # criterion id -> (score or None, rationale) as last saved on the server
    "busy": set(),  # probes currently being (re)sent
}


def load_data():
    import json

    report = json.loads(document["report_data"].text)
    for result in report["criteria_results"]:
        cid = result["criterion"]["id"]
        state["results"][cid] = result
        state["saved"][cid] = (result["score"], result["rationale"] or "")


def panel_of(cid):
    return document.select_one(f'section[data-criterion-id="{cid}"]')


def current_cid():
    return panels[state["index"]].attrs["data-criterion-id"]


# ---------- scoring ----------


def selected_score(cid):
    for radio in panel_of(cid).select("input[type=radio]"):
        if radio.checked:
            return int(radio.value)
    return None


def rationale_of(cid):
    return document[f"rationale_{cid}"].value.strip()


def is_dirty(cid):
    return (selected_score(cid), rationale_of(cid)) != state["saved"][cid]


def any_dirty():
    return any(is_dirty(cid) for cid in state["saved"])


def refresh_progress():
    scored = 0
    for step in steps:
        cid = step.attrs["data-criterion-id"]
        done = state["saved"][cid][0] is not None
        scored += 1 if done else 0
        active = int(step.attrs["data-step"]) == state["index"]
        cls = "step w-9 h-9 rounded-lg border text-xs font-mono font-semibold transition-colors "
        cls += "bg-emerald-50 border-emerald-300 text-emerald-700 " if done else "bg-white border-slate-200 text-slate-600 "
        cls += "ring-2 ring-indigo-500 " if active else "hover:border-indigo-400 "
        step.className = cls
        step.text = ("✓ " if done else "") + str(int(step.attrs["data-step"]) + 1)
    document["scored_count"].text = str(scored)
    complete_btn.disabled = scored < len(panels)


def show(index, force=False):
    if not force and index != state["index"] and is_dirty(current_cid()):
        if not window.confirm("มีการแก้ไขที่ยังไม่ได้บันทึกในข้อนี้ — ไปข้ออื่นโดยไม่บันทึก?"):
            return
    index = max(0, min(index, len(panels) - 1))
    state["index"] = index
    for i, panel in enumerate(panels):
        if i == index:
            panel.classList.remove("hidden")
        else:
            panel.classList.add("hidden")
    panel = panels[index]
    panel.select_one("[data-prev]").disabled = index == 0
    panel.select_one("[data-next]").disabled = index == len(panels) - 1
    refresh_progress()
    window.scrollTo(0, 0)


def make_save(cid):
    def handler(ev):
        score = selected_score(cid)
        if score is None:
            show_toast("กรุณาเลือกระดับคะแนนตาม rubric", True)
            return
        btn = ev.currentTarget
        btn.disabled = True

        def ok(_):
            btn.disabled = False
            state["saved"][cid] = (score, rationale_of(cid))
            refresh_progress()
            show_toast("บันทึกแล้ว")
            if state["index"] < len(panels) - 1:
                show(state["index"] + 1, force=True)

        def failed(req):
            btn.disabled = False
            show_toast(error_detail(req), True)

        request(
            "put",
            f"/api/assessment/reports/update/{report_id}/criteria/{cid}",
            ok,
            data={"score": score, "rationale": rationale_of(cid)},
            on_error=failed,
        )

    return handler


def on_complete(ev):
    if any_dirty() and not window.confirm("มีข้อที่แก้ไขแล้วแต่ยังไม่ได้บันทึก (จะไม่ถูกนับ) — ส่งผลการประเมินต่อ?"):
        return
    if not window.confirm("ส่งผลการประเมิน? หลังส่งแล้วจะแก้ไขคะแนนไม่ได้"):
        return
    complete_btn.disabled = True

    def ok(_):
        state["saved"] = {}  # nothing left to lose: don't ask before leaving
        window.location.href = f"/assessment/{llm_id}?report={report_id}"

    def failed(req):
        complete_btn.disabled = False
        show_toast(error_detail(req), True)

    request("post", f"/api/assessment/reports/{report_id}/complete", ok, on_error=failed)


# ---------- MEASURE probes ----------


def probe_card(cid, number, probe):
    card = html.DIV(Class="rounded-xl border border-slate-200 bg-slate-50/60 p-3 space-y-2")
    head = html.DIV(Class="flex items-center gap-2")
    head <= html.SPAN(f"Prompt {number}", Class="text-[11px] font-semibold text-slate-500")
    if probe["source"] == "custom":
        head <= html.SPAN("เพิ่มเอง", Class="badge badge-xs badge-info badge-soft")
    busy = probe["id"] in state["busy"]

    actions = html.DIV(Class="ml-auto flex items-center gap-1")
    rerun = html.BUTTON(
        [html.I(Class="ph ph-arrow-clockwise"), " ส่งใหม่"], type="button", Class="btn btn-xs btn-ghost"
    )
    rerun.disabled = busy
    rerun.bind("click", lambda ev, cid=cid, probe=probe: rerun_probe(cid, probe))
    actions <= rerun
    if probe["source"] == "custom":
        delete = html.BUTTON(html.I(Class="ph ph-trash"), type="button", Class="btn btn-xs btn-ghost text-rose-600", title="ลบ prompt นี้")
        delete.disabled = busy
        delete.bind("click", lambda ev, cid=cid, probe=probe: delete_probe(cid, probe))
        actions <= delete
    head <= actions
    card <= head

    prompt = html.DIV(Class="text-xs font-mono text-slate-600 whitespace-pre-wrap")
    prompt.text = probe["prompt"]
    card <= prompt

    if busy:
        card <= html.DIV([html.SPAN(Class="loading loading-spinner loading-xs"), " กำลังส่งให้โมเดล…"], Class="text-xs text-slate-500")
    elif probe["response"]:
        body = html.DIV(Class="md-content rounded-lg bg-white border border-slate-200 p-3")
        body.innerHTML = window.matini.renderMarkdown(probe["response"])
        card <= body
    if probe["error"] and not busy:
        error = html.DIV(Class="text-xs text-rose-700")
        error.text = "โมเดลไม่ตอบ: " + probe["error"]
        card <= error
    return card


def render_probes(cid):
    container = document.select_one(f'[data-probes="{cid}"]')
    container.clear()
    probes = state["results"][cid]["probes"]
    if not probes:
        container <= html.P(
            "ยังไม่มีคำตอบจากโมเดล (งานส่งคำถามอาจถูกขัดจังหวะ) — เพิ่ม prompt ทดสอบเองด้านล่างได้",
            Class="text-xs text-amber-700",
        )
    for number, probe in enumerate(probes, start=1):
        container <= probe_card(cid, number, probe)


def replace_probe(cid, probe):
    probes = state["results"][cid]["probes"]
    for i, current in enumerate(probes):
        if current["id"] == probe["id"]:
            probes[i] = probe
            return


def rerun_probe(cid, probe):
    state["busy"].add(probe["id"])
    render_probes(cid)

    def ok(fresh):
        state["busy"].discard(probe["id"])
        replace_probe(cid, fresh)
        render_probes(cid)

    def failed(req):
        state["busy"].discard(probe["id"])
        render_probes(cid)
        show_toast(error_detail(req), True)

    request(
        "post",
        f"/api/assessment/reports/{report_id}/criteria/{cid}/probes/{probe['id']}/rerun",
        ok,
        on_error=failed,
        timeout=PROBE_TIMEOUT_S,
    )


def delete_probe(cid, probe):
    if not window.confirm("ลบ prompt ที่เพิ่มเองนี้?"):
        return

    def ok(_):
        state["results"][cid]["probes"] = [p for p in state["results"][cid]["probes"] if p["id"] != probe["id"]]
        render_probes(cid)

    request(
        "delete", f"/api/assessment/reports/{report_id}/criteria/{cid}/probes/delete/{probe['id']}", ok
    )


def make_add_probe(cid):
    def handler(ev):
        box = document[f"custom_{cid}"]
        prompt = box.value.strip()
        if not prompt:
            show_toast("กรุณาพิมพ์ prompt ที่ต้องการทดสอบ", True)
            return
        btn = ev.currentTarget
        btn.disabled = True
        box.disabled = True
        btn.text = "กำลังส่งให้โมเดล…"

        def done():
            btn.disabled = False
            box.disabled = False
            btn.clear()
            btn <= html.I(Class="ph ph-paper-plane-right")
            btn <= " ส่งให้โมเดล"

        def ok(probe):
            done()
            box.value = ""
            state["results"][cid]["probes"].append(probe)
            render_probes(cid)
            if probe["error"]:
                show_toast("โมเดลไม่ตอบ: " + probe["error"], True)

        def failed(req):
            done()
            show_toast(error_detail(req), True)

        request(
            "post",
            f"/api/assessment/reports/{report_id}/criteria/{cid}/probes/create",
            ok,
            data={"prompt": prompt},
            on_error=failed,
            timeout=PROBE_TIMEOUT_S,
        )

    return handler


# ---------- document viewer ----------


def make_open_file(panel, button):
    file_id = button.attrs["data-open-file"]
    filename = button.attrs["data-filename"]

    def handler(ev):
        viewer = panel.select_one(".viewer")
        body = viewer.select_one(".viewer-body")
        text_btn = viewer.select_one(".viewer-text")
        viewer.classList.remove("hidden")
        viewer.select_one(".viewer-title").text = filename
        viewer.select_one(".viewer-download").href = f"{api_url()}/api/evidence-files/{file_id}/download"
        body.clear()
        text_btn.classList.add("hidden")
        body <= html.P("กำลังโหลด…", Class="text-xs text-slate-400")
        viewer.scrollIntoView()

        def show_text(meta):
            body.clear()
            text = meta["text_preview"] or ("ไม่มีข้อความที่ดึงได้จากไฟล์นี้: " + (meta["extract_error"] or "-"))
            pre = html.PRE(Class="text-xs whitespace-pre-wrap bg-white border border-slate-200 rounded-lg p-3 max-h-[70vh] overflow-auto")
            pre.text = text
            body <= pre

        def ok(meta):
            if meta["content_type"] == "application/pdf" or meta["filename"].lower().endswith(".pdf"):
                body.clear()
                body <= html.IFRAME(
                    src=f"{api_url()}/api/evidence-files/{file_id}/download?inline=true",
                    Class="w-full h-[70vh] rounded-lg border border-slate-200 bg-white",
                )
                text_btn.classList.remove("hidden")
                text_btn.unbind("click")
                text_btn.bind("click", lambda ev: show_text(meta))
            else:
                show_text(meta)

        def missing(req):
            body.clear()
            body <= html.P("ไม่พบไฟล์นี้ (อาจถูกลบไปแล้ว)", Class="text-xs text-rose-600")

        request("get", f"/api/evidence-files/{file_id}?full=true", ok, on_error=missing)

    return handler


def make_close_viewer(panel):
    def handler(ev):
        panel.select_one(".viewer").classList.add("hidden")
        panel.select_one(".viewer-body").clear()

    return handler


# ---------- wiring ----------


def on_before_unload(ev):
    if any_dirty():
        ev.preventDefault()
        ev.returnValue = ""


def init():
    load_data()
    for step in steps:
        step.bind("click", lambda ev, step=step: show(int(step.attrs["data-step"])))
    for panel in panels:
        cid = panel.attrs["data-criterion-id"]
        panel.select_one("[data-save]").bind("click", make_save(cid))
        panel.select_one("[data-prev]").bind("click", lambda ev: show(state["index"] - 1))
        panel.select_one("[data-next]").bind("click", lambda ev: show(state["index"] + 1))
        for button in panel.select("[data-open-file]"):
            button.bind("click", make_open_file(panel, button))
        panel.select_one(".viewer-close").bind("click", make_close_viewer(panel))
        add = panel.select_one("[data-add-probe]")
        if add is not None:
            add.bind("click", make_add_probe(cid))
            render_probes(cid)
    complete_btn.bind("click", on_complete)
    window.bind("beforeunload", on_before_unload)
    # resume where the assessor left off: the first criterion without a score
    first_open = [i for i, p in enumerate(panels) if state["saved"][p.attrs["data-criterion-id"]][0] is None]
    show(first_open[0] if first_open else 0, force=True)


init()
