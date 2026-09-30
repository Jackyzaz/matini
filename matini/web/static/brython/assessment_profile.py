"""Assessment profile modal on the Admin page: the structured NIST AI RMF evidence of one LLM.

Editing happens on a working copy in `state["profile"]`; "บันทึก" sends the whole profile in a single
PUT. Uploads go through `window.matini.uploadFile` (multipart, which `common.request()` can't send).
`json` is imported inside functions on purpose: see the "Brython gotchas" in CLAUDE.md.
"""
from browser import document, html, window

from common import api_url, error_detail, request, show_toast

MAX_UPLOAD_MB = 8

TABS = [("context", "บริบทระบบ"), ("GOVERN", "GOVERN"), ("MAP", "MAP"), ("MEASURE", "MEASURE"), ("MANAGE", "MANAGE")]
STATUS_OPTIONS = [
    ("unknown", "ไม่ระบุ"),
    ("implemented", "ดำเนินการแล้ว"),
    ("partial", "ดำเนินการบางส่วน"),
    ("not_implemented", "ยังไม่ได้ดำเนินการ"),
]
CONTEXT_FIELDS = [
    ("intended_use", "วัตถุประสงค์การใช้งาน", "ระบบนี้ใช้ทำอะไร เช่น ผู้ช่วยตอบคำถามเกี่ยวกับระเบียบของมหาวิทยาลัย"),
    ("target_users", "กลุ่มผู้ใช้", "ใครเป็นผู้ใช้ เช่น นักศึกษา บุคลากร ประชาชนทั่วไป"),
    ("out_of_scope_use", "การใช้งานที่อยู่นอกขอบเขต", "การใช้งานที่ไม่ควรทำ เช่น ให้คำปรึกษาทางการแพทย์หรือกฎหมาย"),
    ("data_sources", "แหล่งข้อมูล", "ข้อมูลที่ใช้ฝึก/ปรับแต่ง/อ้างอิง และข้อมูลจากบุคคลที่สาม"),
    ("deployment_context", "บริบทการนำไปใช้", "ติดตั้งที่ไหน ใครดูแล มีมนุษย์ตรวจสอบผลลัพธ์หรือไม่"),
    ("notes", "หมายเหตุอื่น ๆ", "ข้อมูลอื่นที่ผู้ตัดสินควรรู้"),
]
KIND_ICONS = {"document": "ph-file-text", "link": "ph-link", "text": "ph-text-align-left"}

INPUT_CLS = "w-full text-xs p-2.5 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
LABEL_CLS = "block text-[11px] font-semibold text-slate-700 mb-1.5"

dialog = document["profile_modal"]
tabs_el = document["profile_tabs"]
body_el = document["profile_body"]
file_input = document["profile_file_input"]

state = {
    "llm": None,
    "profile": None,
    "criteria": None,  # fetched once from /api/assessment/criteria
    "tab": "context",
    "dirty": False,
    "files": {},  # file_id -> metadata dict, or "missing"
    "uploaded": set(),  # files uploaded since the last save; deleted again if they never get saved
    "upload_target": None,  # criterion id the file picker was opened for
}


# ---------- state helpers ----------


def normalize(profile):
    """Fill in defaults so the UI can index every field."""
    profile.setdefault("system_context", {})
    for key, _, _ in CONTEXT_FIELDS:
        profile["system_context"].setdefault(key, "")
    profile.setdefault("criteria", {})
    return profile


def criterion_evidence(cid):
    return state["profile"]["criteria"].setdefault(cid, {"status": "unknown", "notes": "", "items": []})


def is_filled(evidence):
    return evidence["status"] != "unknown" or bool(evidence["notes"].strip()) or len(evidence["items"]) > 0


def tab_progress(tab):
    """(filled, total) for a tab's badge."""
    if tab == "context":
        context = state["profile"]["system_context"]
        return len([k for k, _, _ in CONTEXT_FIELDS if context[k].strip()]), len(CONTEXT_FIELDS)
    ids = [c["id"] for c in state["criteria"] if c["nist_function"] == tab]
    profile_criteria = state["profile"]["criteria"]
    return len([i for i in ids if i in profile_criteria and is_filled(profile_criteria[i])]), len(ids)


def mark_dirty():
    state["dirty"] = True
    document["profile_dirty"].classList.remove("hidden")
    render_tabs()


# ---------- small DOM builders ----------


def labelled(label, control, hint=None):
    wrap = html.DIV()
    text = html.LABEL(label, Class=LABEL_CLS)
    if hint:
        text <= html.SPAN(" " + hint, Class="font-normal text-slate-400")
    wrap <= text
    wrap <= control
    return wrap


def text_input(target, key, placeholder="", cls=INPUT_CLS, input_type="text"):
    el = html.INPUT(type=input_type, placeholder=placeholder, Class=cls)
    el.value = target.get(key) or ""

    def on_input(ev):
        target[key] = el.value
        mark_dirty()

    el.bind("input", on_input)
    return el


def text_area(target, key, placeholder="", rows=3):
    el = html.TEXTAREA(rows=rows, placeholder=placeholder, Class=INPUT_CLS)
    el.value = target.get(key) or ""

    def on_input(ev):
        target[key] = el.value
        mark_dirty()

    el.bind("input", on_input)
    return el


def small_button(icon, label, handler, cls="btn-ghost"):
    btn = html.BUTTON(
        [html.I(Class=f"ph {icon}"), " " + label if label else ""],
        type="button",
        Class=f"btn btn-xs {cls}",
    )
    btn.bind("click", handler)
    return btn


# ---------- rendering ----------


def render_tabs():
    tabs_el.clear()
    for tab, label in TABS:
        done, total = tab_progress(tab)
        btn = html.BUTTON(label, type="button", role="tab", Class="tab" + (" tab-active" if tab == state["tab"] else ""))
        btn <= html.SPAN(f"{done}/{total}", Class="badge badge-sm ml-1.5 " + ("badge-primary" if total and done == total else "badge-ghost"))

        def switch(ev, tab=tab):
            state["tab"] = tab
            render_tabs()
            render_body(reset_scroll=True)

        btn.bind("click", switch)
        tabs_el <= btn


def render_body(reset_scroll=False):
    body_el.clear()
    if reset_scroll:
        body_el.scrollTop = 0
    if state["tab"] == "context":
        render_context()
    else:
        render_function(state["tab"])


def render_context():
    body_el <= html.P(
        "อธิบายระบบโดยรวม — ผู้ตัดสินจะได้รับบริบทนี้ประกอบทุกเกณฑ์ (เว้นว่างได้)",
        Class="text-xs text-slate-500",
    )
    grid = html.DIV(Class="grid grid-cols-1 md:grid-cols-2 gap-4")
    for key, label, placeholder in CONTEXT_FIELDS:
        grid <= labelled(label, text_area(state["profile"]["system_context"], key, placeholder, rows=4))
    body_el <= grid


def render_function(fn):
    criteria = [c for c in state["criteria"] if c["nist_function"] == fn]
    if fn == "MEASURE":
        body_el <= html.P(
            "MEASURE ใช้ผลทดสอบอัตโนมัติ (probe) อยู่แล้ว — ช่องนี้ไว้แนบผล benchmark หรือรายงานการทดสอบจากภายนอกเพิ่มเติม",
            Class="text-xs text-slate-500",
        )
    for criterion in criteria:
        body_el <= criterion_card(criterion)


def criterion_card(criterion):
    cid = criterion["id"]
    evidence = criterion_evidence(cid)
    card = html.DIV(Class="bg-white rounded-xl border border-slate-200 p-4 space-y-3")

    head = html.DIV()
    head <= html.DIV(f"{criterion['nist_category']} • {criterion['ethics_dimension']}", Class="text-[10px] font-mono text-slate-400")
    title = html.DIV(Class="text-sm font-bold text-slate-900")
    title.text = criterion["title"]
    head <= title
    question = html.P(Class="text-xs text-slate-600 mt-0.5")
    question.text = criterion["guiding_question"]
    head <= question
    card <= head

    status = html.SELECT([html.OPTION(label, value=value) for value, label in STATUS_OPTIONS], Class="select select-sm w-full bg-white border-slate-200 text-xs")
    status.value = evidence["status"]

    def on_status(ev):
        evidence["status"] = status.value
        mark_dirty()

    status.bind("input", on_status)

    row = html.DIV(Class="grid grid-cols-1 md:grid-cols-3 gap-3")
    row <= labelled("สถานะการดำเนินการ", status, "(คำประกาศของผู้กรอก)")
    notes = labelled("บันทึก/คำอธิบาย", text_area(evidence, "notes", "สรุปสิ่งที่ทำไว้ หรือเหตุผลที่ยังไม่ได้ทำ", rows=2))
    notes.classList.add("md:col-span-2")
    row <= notes
    card <= row

    items = html.DIV(Class="space-y-2")
    for index in range(len(evidence["items"])):
        items <= item_row(cid, evidence, index)
    card <= items

    add = html.DIV(Class="flex items-center gap-1.5 flex-wrap")
    add <= html.SPAN("เพิ่มหลักฐาน:", Class="text-[11px] font-semibold text-slate-500 mr-1")
    add <= small_button("ph-link", "ลิงก์", lambda ev: add_item(cid, "link"), "btn-outline")
    add <= small_button("ph-text-align-left", "ข้อความ", lambda ev: add_item(cid, "text"), "btn-outline")
    add <= small_button("ph-paperclip", "ไฟล์", lambda ev: pick_file(cid), "btn-outline")
    add <= html.SPAN(f"PDF / DOCX / TXT / MD ไม่เกิน {MAX_UPLOAD_MB} MB", Class="text-[10px] text-slate-400 ml-1")
    card <= add
    return card


def item_row(cid, evidence, index):
    item = evidence["items"][index]
    kind = item["kind"]
    row = html.DIV(Class="rounded-lg border border-slate-200 bg-slate-50/70 p-3 space-y-2")

    head = html.DIV(Class="flex items-center gap-2")
    head <= html.I(Class=f"ph {KIND_ICONS[kind]} text-base text-slate-500 shrink-0", title=kind)
    head <= text_input(item, "title", "ชื่อหลักฐาน", INPUT_CLS + " flex-1")

    date_input = html.INPUT(type="date", title="วันที่ของเอกสาร", Class=INPUT_CLS + " w-36! shrink-0")
    date_input.value = item.get("doc_date") or ""

    def on_date(ev):
        item["doc_date"] = date_input.value or None
        mark_dirty()

    date_input.bind("input", on_date)
    head <= date_input

    def remove(ev):
        del evidence["items"][index]
        mark_dirty()
        render_body()

    head <= small_button("ph-trash", "", remove, "btn-ghost text-rose-600")
    row <= head

    if kind == "link":
        row <= text_input(item, "url", "https://…", INPUT_CLS + " font-mono", "url")
    elif kind == "document":
        row <= file_info(item)

    placeholder = {
        "document": "สรุปย่อของเอกสาร (เว้นว่าง = ใช้ข้อความที่ดึงจากไฟล์)",
        "link": "ข้อความสำคัญจากลิงก์นี้ (ถ้ามี)",
        "text": "พิมพ์หลักฐานเป็นข้อความ",
    }[kind]
    row <= text_area(item, "excerpt", placeholder, rows=2)
    return row


def file_info(item):
    info = html.DIV(Class="flex items-center gap-2 flex-wrap text-[11px]")
    meta = state["files"].get(item["file_id"])
    if meta is None:
        info <= html.SPAN("กำลังโหลดข้อมูลไฟล์…", Class="text-slate-400")
    elif meta == "missing":
        info <= html.SPAN("ไม่พบไฟล์ (อาจถูกลบแล้ว) — ลบรายการนี้แล้วอัปโหลดใหม่", Class="text-rose-600")
    else:
        link = html.A(
            [html.I(Class="ph ph-download-simple"), " " + meta["filename"]],
            href=f"{api_url()}/api/evidence-files/{meta['id']}/download",
            target="_blank",
            Class="font-mono text-indigo-600 hover:underline",
        )
        info <= link
        info <= html.SPAN(format_size(meta["size"]), Class="text-slate-400")
        if not meta["has_text"]:
            badge = html.SPAN("ดึงข้อความไม่ได้", Class="badge badge-warning badge-soft badge-sm")
            badge.attrs["title"] = meta["extract_error"] or ""
            info <= badge
            info <= html.SPAN(meta["extract_error"] or "", Class="text-amber-700")
    return info


def format_size(size):
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{max(1, round(size / 1024))} KB"


# ---------- evidence items and uploads ----------


def add_item(cid, kind, **fields):
    item = {"kind": kind, "title": "", "url": "", "excerpt": "", "doc_date": None, "file_id": None}
    item.update(fields)
    criterion_evidence(cid)["items"].append(item)
    mark_dirty()
    render_body()


def pick_file(cid):
    state["upload_target"] = cid
    file_input.click()


def on_file_chosen(ev):
    file = file_input.files.item(0)
    file_input.value = ""  # lets the same file be picked again
    cid = state["upload_target"]
    if file is None or state["llm"] is None or cid is None:
        return
    if file.size > MAX_UPLOAD_MB * 1024 * 1024:
        show_toast(f"ไฟล์ใหญ่เกิน {MAX_UPLOAD_MB} MB", True)
        return
    show_toast(f"กำลังอัปโหลด {file.name}…")

    def ok(text):
        import json

        meta = json.loads(text)
        state["files"][meta["id"]] = meta
        if state["profile"] is None or state["llm"] is None:
            # the modal was closed while uploading: nothing will ever reference this file
            request("delete", "/api/evidence-files/delete/" + meta["id"], lambda _: None, on_error=lambda req: None)
            return
        state["uploaded"].add(meta["id"])
        add_item(cid, "document", title=meta["filename"], file_id=meta["id"])
        if meta["has_text"]:
            show_toast(f"อัปโหลด {meta['filename']} แล้ว และดึงข้อความสำเร็จ")
        else:
            show_toast(f"อัปโหลด {meta['filename']} แล้ว แต่ {meta['extract_error']}", True)

    def failed(message):
        show_toast("อัปโหลดไม่สำเร็จ: " + message, True)

    window.matini.uploadFile(f"{api_url()}/api/evidence-files/upload?llm_id={state['llm']['id']}", file, ok, failed)


def load_file_meta():
    """Metadata (name, size, extraction result) of the files the saved profile already references."""
    ids = set()
    for evidence in state["profile"]["criteria"].values():
        for item in evidence["items"]:
            if item["file_id"] and item["file_id"] not in state["files"]:
                ids.add(item["file_id"])
    for file_id in ids:
        request(
            "get",
            "/api/evidence-files/" + file_id,
            lambda meta: loaded(meta["id"], meta),
            on_error=lambda req, file_id=file_id: loaded(file_id, "missing"),
        )


def loaded(file_id, meta):
    state["files"][file_id] = meta
    if state["profile"] is not None and state["tab"] != "context":
        render_body()


def discard_unsaved_uploads():
    for file_id in state["uploaded"]:
        request("delete", "/api/evidence-files/delete/" + file_id, lambda _: None, on_error=lambda req: None)
    state["uploaded"] = set()


# ---------- open / save / close ----------


def open_profile(llm_id):
    def got_llm(llm):
        state["llm"] = llm
        state["profile"] = normalize(llm["assessment_profile"])
        state.update(tab="context", dirty=False, files={}, uploaded=set())
        document["profile_llm_name"].text = llm["name"]
        document["profile_dirty"].classList.add("hidden")
        show_updated()
        render_tabs()
        render_body(reset_scroll=True)
        if not dialog.open:
            dialog.showModal()
        load_file_meta()

    def got_criteria(criteria):
        state["criteria"] = criteria
        request("get", "/api/llms/" + llm_id, got_llm)

    if state["criteria"] is None:
        request("get", "/api/assessment/criteria", got_criteria)
    else:
        request("get", "/api/llms/" + llm_id, got_llm)


def show_updated():
    updated = state["profile"].get("updated_date")
    document["profile_updated"].text = (
        "บันทึกล่าสุด " + updated[:16].replace("T", " ") if updated else "ยังไม่เคยบันทึกข้อมูลการประเมิน"
    )


def build_payload():
    """Only what was actually filled in: unfilled criteria and empty free-text items are dropped."""
    profile = state["profile"]
    criteria = {}
    for cid, evidence in profile["criteria"].items():
        items = [
            item
            for item in evidence["items"]
            if item["kind"] == "document" or item["title"].strip() or item["url"].strip() or item["excerpt"].strip()
        ]
        cleaned = {"status": evidence["status"], "notes": evidence["notes"], "items": items}
        if is_filled(cleaned):
            criteria[cid] = cleaned
    return {"system_context": profile["system_context"], "criteria": criteria}


def save(ev):
    if state["llm"] is None:
        return
    btn = document["profile_save"]
    btn.disabled = True

    def ok(llm):
        btn.disabled = False
        state["llm"] = llm
        state["profile"] = normalize(llm["assessment_profile"])
        state["dirty"] = False
        referenced = {
            item["file_id"] for evidence in state["profile"]["criteria"].values() for item in evidence["items"]
        }
        # files uploaded this session but dropped before saving can't be part of any report
        for file_id in [f for f in state["uploaded"] if f not in referenced]:
            request("delete", "/api/evidence-files/delete/" + file_id, lambda _: None, on_error=lambda req: None)
        state["uploaded"] = set()
        document["profile_dirty"].classList.add("hidden")
        show_updated()
        render_tabs()
        render_body()
        show_toast("บันทึกข้อมูลการประเมินแล้ว")

    def failed(req):
        btn.disabled = False
        show_toast(error_detail(req), True)

    request("put", f"/api/llms/update/{state['llm']['id']}/profile", ok, data=build_payload(), on_error=failed)


def close_dialog():
    from javascript import NULL

    discard_unsaved_uploads()
    state.update(llm=None, profile=None, dirty=False)
    dialog.close()
    if "profile=" in window.location.search:
        window.history.replaceState(NULL, "", window.location.pathname)  # a reload shouldn't reopen it


def try_close(ev=None):
    if ev is not None:
        ev.preventDefault()  # also stops the Esc key from closing the dialog before we've asked
    if state["dirty"] and not window.confirm("มีข้อมูลที่ยังไม่ได้บันทึก — ปิดโดยไม่บันทึก?"):
        return
    close_dialog()


document["profile_save"].bind("click", save)
document["profile_close"].bind("click", try_close)
document["profile_cancel"].bind("click", try_close)
dialog.bind("cancel", try_close)
file_input.bind("change", on_file_chosen)
