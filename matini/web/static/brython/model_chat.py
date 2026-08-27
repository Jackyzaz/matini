from browser import document, ajax, window, html
import json
import time

def show_toast(message, is_error=False):
    toast_container = document["toast_container"]
    bg_class = "bg-rose-50 border-rose-200 text-rose-800" if is_error else "bg-emerald-50 border-emerald-200 text-emerald-800"
    icon_name = "ph-warning-circle" if is_error else "ph-check-circle"
    
    toast = html.DIV(
        html.DIV(
            [
                html.I(Class=f"ph {icon_name} text-xl mr-2 font-bold"),
                html.SPAN(message, Class="text-sm font-medium"),
            ],
            Class=f"flex items-center p-4 rounded-xl border shadow-lg backdrop-blur-md {bg_class} animate-bounce"
        ),
        Class="mb-3 transition-all duration-300 transform translate-y-0"
    )
    toast_container <= toast
    
    # Auto dismiss after 3.5 seconds
    def remove_toast():
        try:
            toast.remove()
        except:
            pass
    window.setTimeout(remove_toast, 3500)

def append_chat_message(role, content, status="allowed"):
    chat_box = document["chat_history"]
    timestamp = time.strftime("%H:%M:%S")
    
    if role == "user":
        msg_html = html.DIV(
            [
                html.DIV(
                    [
                        html.SPAN("You", Class="text-xs font-semibold text-slate-500 mr-2"),
                        html.SPAN(timestamp, Class="text-[11px] text-slate-400"),
                    ],
                    Class="flex items-center justify-end mb-1"
                ),
                html.DIV(
                    html.P(content, Class="text-sm text-white font-normal whitespace-pre-wrap leading-relaxed"),
                    Class="bg-slate-900 text-white rounded-2xl rounded-tr-none px-4 py-3 shadow-sm inline-block max-w-[85%]"
                )
            ],
            Class="flex flex-col items-end mb-4 animate-fade-in"
        )
    else:
        # AI or System
        if status == "blocked":
            bubble_class = "bg-rose-50 border border-rose-200/80 text-rose-900"
            badge = html.SPAN("BLOCKED BY GUARDRAIL", Class="px-2 py-0.5 text-[10px] font-bold tracking-wider bg-rose-200/70 text-rose-800 rounded-full mr-2")
        else:
            bubble_class = "bg-white border border-slate-200/90 text-slate-800 shadow-sm"
            badge = html.SPAN("GUARDRAIL PASSED", Class="px-2 py-0.5 text-[10px] font-bold tracking-wider bg-emerald-100 text-emerald-800 rounded-full mr-2")
            
        model_name = document["model_name_header"].text
        
        msg_html = html.DIV(
            [
                html.DIV(
                    [
                        badge,
                        html.SPAN(model_name, Class="text-xs font-semibold text-slate-700 mr-2"),
                        html.SPAN(timestamp, Class="text-[11px] text-slate-400"),
                    ],
                    Class="flex items-center mb-1.5"
                ),
                html.DIV(
                    html.PRE(content, Class="text-xs md:text-sm font-mono whitespace-pre-wrap leading-relaxed overflow-x-auto") if status != "blocked" else html.P(content, Class="text-sm leading-relaxed"),
                    Class=f"rounded-2xl rounded-tl-none p-4.5 max-w-[92%] {bubble_class}"
                )
            ],
            Class="flex flex-col items-start mb-4 animate-fade-in"
        )
        
    chat_box <= msg_html
    chat_box.scrollTop = chat_box.scrollHeight

def render_guardrail_inspector(results, total_latency, status):
    inspector = document["guardrail_inspector"]
    inspector.clear()
    
    # Header summary
    status_color = "text-emerald-700 bg-emerald-50 border-emerald-200" if status == "allowed" else "text-rose-700 bg-rose-50 border-rose-200"
    status_icon = "ph-shield-check" if status == "allowed" else "ph-shield-warning"
    
    summary_card = html.DIV(
        [
            html.DIV(
                [
                    html.I(Class=f"ph {status_icon} text-2xl mr-3 font-bold"),
                    html.DIV(
                        [
                            html.DIV(f"Pipeline Result: {status.upper()}", Class="font-bold text-sm"),
                            html.DIV(f"Total Inspection Latency: {total_latency} ms", Class="text-xs opacity-80 mt-0.5"),
                        ]
                    ),
                ],
                Class="flex items-center"
            )
        ],
        Class=f"p-3.5 rounded-xl border mb-4 {status_color}"
    )
    inspector <= summary_card
    
    # Detailed Layers
    for res in results:
        layer_passed = res.get("passed", False)
        badge_bg = "bg-emerald-100 text-emerald-800" if layer_passed else "bg-rose-100 text-rose-800"
        status_text = "PASS" if layer_passed else "FAIL / BLOCKED"
        border_col = "border-slate-200" if layer_passed else "border-rose-200 bg-rose-50/30"
        
        triggers = res.get("detected_triggers", [])
        triggers_elem = None
        if triggers:
            triggers_elem = html.DIV(
                [
                    html.SPAN("Triggers: ", Class="text-[11px] font-semibold text-rose-700"),
                    html.SPAN(", ".join(triggers), Class="text-[11px] text-rose-600 font-mono"),
                ],
                Class="mt-1.5 pt-1.5 border-t border-rose-100"
            )

        layer_card = html.DIV(
            [
                html.DIV(
                    [
                        html.SPAN(res.get("layer", "Guardrail Layer"), Class="font-semibold text-xs text-slate-800"),
                        html.SPAN(f"{res.get('latency_ms', 0)} ms", Class="text-[11px] text-slate-400 font-mono ml-auto mr-2"),
                        html.SPAN(status_text, Class=f"text-[10px] font-bold px-2 py-0.5 rounded-full {badge_bg}"),
                    ],
                    Class="flex items-center mb-1"
                ),
                html.P(res.get("reason", ""), Class="text-xs text-slate-600 leading-relaxed"),
                triggers_elem if triggers_elem else "",
            ],
            Class=f"p-3 rounded-xl border bg-white shadow-xs mb-2.5 {border_col}"
        )
        inspector <= layer_card

def send_chat_prompt(evt):
    prompt_input = document["prompt_input"]
    prompt = prompt_input.value.strip()
    if not prompt:
        return
        
    model_id = document["model_id_hidden"].value
    api_url = document["api_url_hidden"].value
    
    # Append User Message to UI
    append_chat_message("user", prompt)
    prompt_input.value = ""
    
    # UI Loading state
    send_btn = document["send_btn"]
    send_btn.disabled = True
    send_btn.innerHTML = '<i class="ph ph-spinner animate-spin text-lg"></i> <span class="ml-1">Verifying...</span>'
    
    def on_complete(req):
        send_btn.disabled = False
        send_btn.innerHTML = '<i class="ph ph-paper-plane-tilt text-lg"></i> <span class="ml-1">Send</span>'
        
        if req.status == 200:
            data = json.loads(req.text)
            status = data.get("status", "allowed")
            total_latency = data.get("total_latency_ms", 0.0)
            guardrail_results = data.get("guardrail_results", [])
            
            if status == "blocked":
                # Find blocked reason
                reasons = [r.get("reason", "") for r in guardrail_results if not r.get("passed", False)]
                blocked_msg = "⚠️ Prompt rejected by Guardrail:\n" + "\n".join(reasons)
                append_chat_message("ai", blocked_msg, status="blocked")
                show_toast("Guardrail Triggered! Prompt blocked safely.", is_error=True)
            else:
                reply = data.get("response", "No response generated.")
                append_chat_message("ai", reply, status="allowed")
                show_toast("Prompt passed all guardrails successfully!")
                
            render_guardrail_inspector(guardrail_results, total_latency, status)
        else:
            show_toast(f"Error communicating with API (Status {req.status})", is_error=True)
            
    req = ajax.ajax()
    req.bind("complete", on_complete)
    req.open("POST", f"{api_url}/api/chat", True)
    req.set_header("content-type", "application/json")
    req.send(json.dumps({"model_id": model_id, "prompt": prompt}))

def save_guardrail_settings(evt):
    model_id = document["model_id_hidden"].value
    api_url = document["api_url_hidden"].value
    
    rule_enabled = document["toggle_rule_based"].checked
    blacklist_raw = document["blacklist_input"].value
    blacklist_words = [w.strip() for w in blacklist_raw.split(",") if w.strip()]
    
    judge_enabled = document["toggle_llm_judge"].checked
    judge_prompt = document["judge_prompt_input"].value
    strictness = document["judge_strictness_select"].value
    
    save_btn = document["save_guardrails_btn"]
    save_btn.disabled = True
    save_btn.innerHTML = '<i class="ph ph-spinner animate-spin mr-1"></i> Saving Policy...'
    
    payload = {
        "rule_based_enabled": rule_enabled,
        "blacklist_words": blacklist_words,
        "llm_judge_enabled": judge_enabled,
        "llm_judge_system_prompt": judge_prompt,
        "llm_judge_strictness": strictness,
    }
    
    def on_save_complete(req):
        save_btn.disabled = False
        save_btn.innerHTML = '<i class="ph ph-floppy-disk mr-1 font-bold"></i> Save Guardrail Configuration'
        
        if req.status == 200:
            show_toast("Guardrail policy updated successfully for this model!")
            # Update header badge
            rule_badge = document["badge_rule_status"]
            judge_badge = document["badge_judge_status"]
            
            if rule_enabled:
                rule_badge.className = "px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/80 flex items-center gap-1.5"
                rule_badge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Rule-Based Active'
            else:
                rule_badge.className = "px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-100 text-slate-500 border border-slate-200 flex items-center gap-1.5"
                rule_badge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span> Rule-Based Disabled'
                
            if judge_enabled:
                judge_badge.className = "px-2.5 py-1 text-xs font-semibold rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200/80 flex items-center gap-1.5"
                judge_badge.innerHTML = f'<span class="w-1.5 h-1.5 rounded-full bg-indigo-500"></span> AI Judge ({strictness.capitalize()})'
            else:
                judge_badge.className = "px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-100 text-slate-500 border border-slate-200 flex items-center gap-1.5"
                judge_badge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span> AI Judge Disabled'
        else:
            show_toast("Failed to update guardrails.", is_error=True)

    req = ajax.ajax()
    req.bind("complete", on_save_complete)
    req.open("POST", f"{api_url}/api/models/{model_id}/guardrails", True)
    req.set_header("content-type", "application/json")
    req.send(json.dumps(payload))

def quick_insert_prompt(prompt_text):
    prompt_input = document["prompt_input"]
    prompt_input.value = prompt_text
    prompt_input.focus()

def init_app():
    # Bind events
    if "send_btn" in document:
        document["send_btn"].bind("click", send_chat_prompt)
        
    if "prompt_input" in document:
        def on_keypress(evt):
            if evt.keyCode == 13 and not evt.shiftKey:
                evt.preventDefault()
                send_chat_prompt(evt)
        document["prompt_input"].bind("keydown", on_keypress)
        
    if "save_guardrails_btn" in document:
        document["save_guardrails_btn"].bind("click", save_guardrail_settings)

    # Bind quick test example prompts
    for btn in document.select(".quick-test-btn"):
        def make_handler(text):
            return lambda evt: quick_insert_prompt(text)
        btn.bind("click", make_handler(btn.attrs.get("data-prompt", "")))

# Auto-run Brython initialization
init_app()
