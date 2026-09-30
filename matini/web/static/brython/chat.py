from browser import bind, document, html, window
from javascript import NULL

from common import api_url, error_detail, request, show_toast

LS_LLM_KEY = "matini.llm_id"

state = {"conversation_id": None, "sending": False, "llm_ids": []}

messages_box = document["messages"]
message_list = document["message_list"]
empty_state = document["empty_state"]
prompt_input = document["prompt_input"]
send_btn = document["send_btn"]
llm_select = document["llm_select"]
conversation_list = document["conversation_list"]
assess_link = document["assess_link"]


# ---------- small helpers ----------

def ls_get(key):
    try:
        return window.localStorage.getItem(key)
    except Exception:
        return None


def ls_set(key, value):
    try:
        window.localStorage.setItem(key, value)
    except Exception:
        pass


def scroll_to_bottom():
    messages_box.scrollTop = messages_box.scrollHeight


def show_messages(has_messages):
    if has_messages:
        empty_state.classList.add("hidden")
    else:
        empty_state.classList.remove("hidden")


def set_sending(sending):
    state["sending"] = sending
    send_btn.disabled = sending or not llm_select.value


def update_assess_link():
    if llm_select.value:
        assess_link.href = "/assessment/" + llm_select.value
        assess_link.classList.remove("hidden")
    else:
        assess_link.classList.add("hidden")
    send_btn.disabled = state["sending"] or not llm_select.value


# ---------- message rendering ----------

def add_user_message(content):
    bubble = html.DIV(Class="bg-slate-100 text-slate-900 rounded-2xl px-4 py-2.5 max-w-[85%] text-sm leading-6 whitespace-pre-wrap break-words")
    bubble.text = content
    message_list <= html.DIV(bubble, Class="flex justify-end")


def add_assistant_message(content="", streaming=False):
    body = html.DIV(Class="md-content text-slate-800")
    if content:
        body.innerHTML = window.matini.renderMarkdown(content)
    if streaming:
        body.classList.add("streaming-caret")
    avatar = html.DIV(
        html.I(Class="ph ph-sparkle text-sm"),
        Class="w-7 h-7 shrink-0 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mt-0.5",
    )
    column = html.DIV(body, Class="min-w-0 flex-1")
    message_list <= html.DIV([avatar, column], Class="flex gap-3")
    return body


def add_error_note(body, message):
    note = html.DIV(Class="mt-2 text-xs text-rose-600")
    note.text = message
    body.parent <= note


def render_conversation(conversation):
    message_list.clear()
    for m in conversation["messages"]:
        if m["role"] == "user":
            add_user_message(m["content"])
        else:
            add_assistant_message(m["content"])
    show_messages(len(conversation["messages"]) > 0)
    document["mobile_title"].text = conversation["title"]
    scroll_to_bottom()


# ---------- LLM select ----------

def fill_llms(data):
    llms = data["llms"]
    state["llm_ids"] = [l["id"] for l in llms]
    llm_select.clear()
    if not llms:
        llm_select <= html.OPTION("ยังไม่มีโมเดล — เพิ่มที่หน้า Admin", value="")
        document["empty_hint"].html = 'ยังไม่มีโมเดลในระบบ — <a class="text-indigo-600 underline" href="/admin/">เพิ่ม LLM ที่หน้า Admin</a> ก่อนเริ่มแชท'
        update_assess_link()
        return
    for l in llms:
        size = l.get("parameter_size_b")
        size_text = f" · {size:g}B" if size else ""
        llm_select <= html.OPTION(f"{l['name']} ({l['model_name']}){size_text}", value=l["id"])
    saved = ls_get(LS_LLM_KEY)
    if saved in state["llm_ids"]:
        llm_select.value = saved
    update_assess_link()


@bind(llm_select, "change")
def on_llm_change(ev):
    ls_set(LS_LLM_KEY, llm_select.value)
    update_assess_link()


# ---------- conversation list ----------

def render_conversation_list(data):
    conversation_list.clear()
    if not data["conversations"]:
        conversation_list <= html.DIV("ยังไม่มีการสนทนา", Class="px-3 py-2 text-xs text-slate-500")
        return
    for c in data["conversations"]:
        active = c["id"] == state["conversation_id"]
        row_class = "group flex items-center gap-1 rounded-lg px-3 py-2 text-sm cursor-pointer transition-colors "
        row_class += "bg-white/15 text-white" if active else "text-slate-300 hover:bg-white/10"
        title = html.SPAN(Class="flex-1 truncate")
        title.text = c["title"]
        del_btn = html.BUTTON(html.I(Class="ph ph-trash"), Class="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-white/15 text-slate-400 hover:text-rose-300", title="ลบ")
        row = html.DIV([title, del_btn], Class=row_class)
        row.bind("click", make_open_handler(c["id"]))
        del_btn.bind("click", make_delete_handler(c["id"]))
        conversation_list <= row


def make_open_handler(conversation_id):
    def handler(ev):
        open_conversation(conversation_id)
        document["sidebar"].classList.add("hidden")
    return handler


def make_delete_handler(conversation_id):
    def handler(ev):
        ev.stopPropagation()
        if not window.confirm("ลบการสนทนานี้?"):
            return

        def done(_):
            if state["conversation_id"] == conversation_id:
                new_chat()
            else:
                load_conversations()

        request("delete", "/api/conversations/delete/" + conversation_id, done)
    return handler


def load_conversations():
    request("get", "/api/conversations", render_conversation_list)


def open_conversation(conversation_id, push=True):
    if state["sending"]:
        show_toast("กำลังรอคำตอบอยู่ รอสักครู่ก่อนสลับแชท", True)
        return

    def loaded(conversation):
        state["conversation_id"] = conversation["id"]
        if conversation["llm_id"] in state["llm_ids"]:
            llm_select.value = conversation["llm_id"]
            update_assess_link()
        render_conversation(conversation)
        if push:
            window.history.pushState(NULL, "", "/c/" + conversation["id"])
        load_conversations()

    def failed(req):
        show_toast("ไม่พบการสนทนานี้", True)
        new_chat()

    request("get", "/api/conversations/" + conversation_id, loaded, on_error=failed)


def new_chat(push=True):
    if state["sending"]:
        return
    state["conversation_id"] = None
    message_list.clear()
    show_messages(False)
    document["mobile_title"].text = "Matini"
    if push:
        window.history.pushState(NULL, "", "/")
    load_conversations()
    prompt_input.focus()


@bind(document["new_chat_btn"], "click")
def on_new_chat(ev):
    new_chat()
    document["sidebar"].classList.add("hidden")


@bind(document["menu_btn"], "click")
def on_menu(ev):
    document["sidebar"].classList.toggle("hidden")


def on_popstate(ev):
    path = window.location.pathname
    if path.startswith("/c/"):
        open_conversation(path[3:], push=False)
    else:
        new_chat(push=False)


window.bind("popstate", on_popstate)


# ---------- sending ----------

def stream_reply(conversation_id, content, llm_id):
    body = add_assistant_message(streaming=True)
    parts = []

    def on_line(line):
        import json  # lazy on purpose: see the "Brython gotchas" note in CLAUDE.md

        data = json.loads(line)
        if "delta" in data:
            parts.append(data["delta"])
            body.innerHTML = window.matini.renderMarkdown("".join(parts))
            scroll_to_bottom()
        elif "error" in data:
            show_toast(data["error"], True)
            add_error_note(body, data["error"])

    def on_end(error):
        body.classList.remove("streaming-caret")
        if error:
            show_toast(error, True)
            add_error_note(body, error)
        set_sending(False)
        load_conversations()
        prompt_input.focus()

    window.matini.streamNdjson(
        request_url(conversation_id),
        {"content": content, "llm_id": llm_id},
        on_line,
        on_end,
    )


def request_url(conversation_id):
    return f"{api_url()}/api/conversations/{conversation_id}/messages"


def send_message():
    content = prompt_input.value.strip()
    llm_id = llm_select.value
    if state["sending"] or not content or not llm_id:
        return
    set_sending(True)
    prompt_input.value = ""
    autosize()

    show_messages(True)
    add_user_message(content)
    scroll_to_bottom()

    def start(conversation_id):
        stream_reply(conversation_id, content, llm_id)

    if state["conversation_id"]:
        start(state["conversation_id"])
        return

    def created(conversation):
        state["conversation_id"] = conversation["id"]
        window.history.pushState(NULL, "", "/c/" + conversation["id"])
        start(conversation["id"])

    def create_failed(req):
        show_toast(error_detail(req), True)
        set_sending(False)

    request("post", "/api/conversations/create", created, data={"llm_id": llm_id}, on_error=create_failed)


def autosize():
    prompt_input.style.height = "auto"
    prompt_input.style.height = f"{min(prompt_input.scrollHeight, 208)}px"


@bind(prompt_input, "input")
def on_input(ev):
    autosize()


@bind(prompt_input, "keydown")
def on_keydown(ev):
    # isComposing: don't send while a Thai/IME composition is being confirmed with Enter
    if ev.key == "Enter" and not ev.shiftKey and not ev.isComposing:
        ev.preventDefault()
        send_message()


@bind(send_btn, "click")
def on_send(ev):
    send_message()


# ---------- init ----------

def init():
    request("get", "/api/llms", fill_llms)
    load_conversations()
    initial = document["initial_conversation_id"].value
    if initial:
        open_conversation(initial, push=False)
    prompt_input.focus()


init()
