from browser import bind, document, html, window

from common import error_detail, request, show_toast

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


def render_table(data):
    tbody.clear()
    if not data["llms"]:
        tbody <= html.TR(
            html.TD("ยังไม่มี LLM — เพิ่มได้จากฟอร์มด้านขวา", colspan="5", Class="px-4 py-8 text-center text-slate-400")
        )
        return
    for llm in data["llms"]:
        active = llm["status"] == "active"
        badge = html.SPAN(
            "เปิดใช้งาน" if active else "ปิดอยู่",
            Class="px-2 py-0.5 rounded-full text-[11px] font-semibold "
            + ("bg-emerald-50 text-emerald-700" if active else "bg-slate-100 text-slate-500"),
        )
        name = html.DIV(Class="font-semibold text-slate-900")
        name.text = llm["name"]
        actions = html.DIV(Class="flex items-center justify-end gap-0.5")
        actions <= html.A(html.I(Class="ph ph-clipboard-text"), href="/assessment/" + llm["id"], Class="p-1.5 rounded-lg text-sm hover:bg-slate-100 text-slate-600", title="ประเมิน NIST AI RMF")
        actions <= action_button("ph-plugs-connected", "ทดสอบการเชื่อมต่อ", make_test(llm))
        actions <= action_button("ph-toggle-left" if active else "ph-toggle-right", "ปิดใช้งาน" if active else "เปิดใช้งาน", make_toggle(llm))
        actions <= action_button("ph-trash", "ลบ", make_delete(llm), "hover:bg-rose-50 text-rose-600")
        tbody <= html.TR(
            [
                cell(name),
                cell(llm["model_name"], "px-4 py-3 font-mono text-slate-700"),
                cell(llm["base_url"] or "(ค่าเริ่มต้นจาก .env)", "px-4 py-3 font-mono text-slate-500"),
                cell(badge),
                cell(actions, "px-4 py-3"),
            ]
        )


def load():
    request("get", "/api/llms?status=all", render_table)


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
        body = {
            "name": llm["name"],
            "provider": llm["provider"],
            "base_url": llm["base_url"],
            "model_name": llm["model_name"],
            "description": llm["description"],
            "status": "inactive" if llm["status"] == "active" else "active",
        }
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
    submit.disabled = True
    body = {
        "name": document["f_name"].value.strip(),
        "model_name": document["f_model"].value.strip(),
        "base_url": document["f_base_url"].value.strip(),
        "description": document["f_description"].value.strip(),
    }

    def ok(_):
        submit.disabled = False
        form.reset()
        show_toast("เพิ่ม LLM แล้ว")
        load()

    def failed(req):
        submit.disabled = False
        show_toast(error_detail(req), True)

    request("post", "/api/llms/create", ok, data=body, on_error=failed)


def set_defaults(data):
    document["f_base_url"].placeholder = data["ollama_base_url"]


request("get", "/api/llms/defaults", set_defaults)
load()
