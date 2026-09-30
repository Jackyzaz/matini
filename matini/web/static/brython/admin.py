from browser import bind, document, html, window

import assessment_profile
from common import error_detail, request, show_toast

editing = {"llm": None}  # the LLM being edited, or None when the form adds a new one

tbody = document["llm_table_body"]
form = document["llm_form"]


def cell(content, cls="px-4 py-3"):
    td = html.TD(Class=cls)
    if isinstance(content, str):
        td.text = content
    else:
        td <= content
    return td


def action_button(icon, title, handler, cls="hover:bg-slate-100 text-slate-600"):
    btn = html.BUTTON(html.I(Class=f"ph {icon}"), Class=f"p-1.5 rounded-lg text-sm {cls}", title=title)
    btn.bind("click", handler)
    return btn


def size_badge(llm):
    if llm.get("parameter_size_b") is None:
        return None
    return html.SPAN(
        format_size(llm["parameter_size_b"]),
        Class="badge badge-primary badge-soft badge-sm font-mono font-semibold",
    )


def format_size(value):
    # 8.0 -> "8B", 3.2 -> "3.2B"
    return (str(int(value)) if value == int(value) else str(value)) + "B"


def render_table(data):
    tbody.clear()
    if editing["llm"]:
        # keep the edit target in sync (e.g. status toggled meanwhile); leave edit mode if it was deleted
        current = [l for l in data["llms"] if l["id"] == editing["llm"]["id"]]
        if current:
            editing["llm"] = current[0]
        else:
            form.reset()
            set_form_mode(None)
    if not data["llms"]:
        tbody <= html.TR(
            html.TD("ยังไม่มี LLM — เพิ่มได้จากฟอร์มด้านขวา", colspan="4", Class="px-4 py-8 text-center text-slate-400")
        )
        return
    for llm in data["llms"]:
        active = llm["status"] == "active"
        badge = html.SPAN(
            "เปิดใช้งาน" if active else "ปิดอยู่",
            Class="px-2.5 py-1 rounded-full text-[11px] font-semibold whitespace-nowrap "
            + ("bg-emerald-50 text-emerald-700" if active else "bg-slate-100 text-slate-500"),
        )
        llm_cell = html.DIV(Class="space-y-1")
        name = html.DIV(Class="font-semibold text-slate-900")
        name.text = llm["name"]
        llm_cell <= name
        tag_row = html.DIV(Class="flex items-center gap-1.5 font-mono text-slate-500")
        tag_row.text = llm["model_name"]
        size = size_badge(llm)
        if size is not None:
            tag_row <= size
        llm_cell <= tag_row
        actions = html.DIV(Class="flex items-center justify-end gap-0.5")
        actions <= html.A(html.I(Class="ph ph-clipboard-text"), href="/assessment/" + llm["id"], Class="p-1.5 rounded-lg text-sm hover:bg-slate-100 text-slate-600", title="ประเมิน NIST AI RMF")
        actions <= action_button("ph-folder-open", "ข้อมูลการประเมิน", make_open_profile(llm))
        actions <= action_button("ph-pencil-simple", "แก้ไข", make_edit(llm))
        actions <= action_button("ph-plugs-connected", "ทดสอบการเชื่อมต่อ", make_test(llm))
        actions <= action_button("ph-toggle-left" if active else "ph-toggle-right", "ปิดใช้งาน" if active else "เปิดใช้งาน", make_toggle(llm))
        actions <= action_button("ph-trash", "ลบ", make_delete(llm), "hover:bg-rose-50 text-rose-600")
        tbody <= html.TR(
            [
                cell(llm_cell),
                cell(llm["base_url"] or "(ค่าเริ่มต้นจาก .env)", "px-4 py-3 font-mono text-slate-500"),
                cell(badge),
                cell(actions, "px-4 py-3"),
            ]
        )


def load():
    request("get", "/api/llms?status=all", render_table)


def set_form_mode(llm):
    editing["llm"] = llm
    is_edit = llm is not None
    document["form_title"].text = "แก้ไข LLM" if is_edit else "เพิ่ม LLM"
    document["f_submit_text"].text = "บันทึกการแก้ไข" if is_edit else "เพิ่ม LLM"
    document["f_submit_icon"].className = "ph ph-floppy-disk" if is_edit else "ph ph-plus"
    if is_edit:
        document["f_cancel"].classList.remove("hidden")
    else:
        document["f_cancel"].classList.add("hidden")


def make_open_profile(llm):
    def handler(ev):
        assessment_profile.open_profile(llm["id"])

    return handler


def make_edit(llm):
    def handler(ev):
        document["f_name"].value = llm["name"]
        document["f_model"].value = llm["model_name"]
        document["f_size"].value = "" if llm.get("parameter_size_b") is None else format_size(llm["parameter_size_b"])[:-1]
        document["f_base_url"].value = llm["base_url"]
        document["f_description"].value = llm["description"]
        set_form_mode(llm)
        document["f_name"].focus()

    return handler


@bind(document["f_cancel"], "click")
def on_cancel(ev):
    form.reset()
    set_form_mode(None)


def make_test(llm):
    def handler(ev):
        btn = ev.currentTarget
        btn.disabled = True
        show_toast(f"กำลังทดสอบ {llm['name']}…")

        def ok(result):
            btn.disabled = False
            if result["ok"]:
                show_toast(f"{llm['name']} ตอบกลับได้ ({result['latency_ms']:.0f} ms)")
            else:
                show_toast(result["error"], True)

        def failed(req):
            btn.disabled = False
            show_toast("ทดสอบไม่สำเร็จ (HTTP " + str(req.status) + ")", True)

        request("post", f"/api/llms/{llm['id']}/test", ok, on_error=failed)

    return handler


def make_toggle(llm):
    def handler(ev):
        # resend every field (the update endpoint replaces them all), flipping only the status
        body = {k: v for k, v in llm.items() if k not in ("id", "assessment_profile")}
        body["status"] = "inactive" if llm["status"] == "active" else "active"
        request("put", "/api/llms/update/" + llm["id"], lambda _: load(), data=body)

    return handler


def make_delete(llm):
    def handler(ev):
        if window.confirm(f"ลบ {llm['name']}?"):
            request("delete", "/api/llms/delete/" + llm["id"], lambda _: load())

    return handler


@bind(form, "submit")
def on_submit(ev):
    ev.preventDefault()
    submit = document["f_submit"]
    size_text = document["f_size"].value.strip()
    submit.disabled = True
    body = {
        "name": document["f_name"].value.strip(),
        "model_name": document["f_model"].value.strip(),
        "parameter_size_b": float(size_text) if size_text else None,
        "base_url": document["f_base_url"].value.strip(),
        "description": document["f_description"].value.strip(),
    }

    def ok(_):
        submit.disabled = False
        show_toast("บันทึกการแก้ไขแล้ว" if editing["llm"] else "เพิ่ม LLM แล้ว")
        form.reset()
        set_form_mode(None)
        load()

    def failed(req):
        submit.disabled = False
        show_toast(error_detail(req), True)

    if editing["llm"]:
        # keep provider and status (enabled/disabled) as they are; the form edits the rest
        body["provider"] = editing["llm"]["provider"]
        body["status"] = editing["llm"]["status"]
        request("put", "/api/llms/update/" + editing["llm"]["id"], ok, data=body, on_error=failed)
    else:
        request("post", "/api/llms/create", ok, data=body, on_error=failed)


def set_defaults(data):
    document["f_base_url"].placeholder = data["ollama_base_url"]


def open_requested_profile():
    """/admin/?profile=<llm_id> opens that LLM's profile straight away (linked from the Assessment page)."""
    for part in window.location.search.lstrip("?").split("&"):
        if part.startswith("profile=") and len(part) > len("profile="):
            assessment_profile.open_profile(part[len("profile="):])


request("get", "/api/llms/defaults", set_defaults)
load()
open_requested_profile()
