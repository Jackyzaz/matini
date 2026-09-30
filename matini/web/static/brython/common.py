"""Helpers shared by the Brython pages (loaded via the pythonpath set in base_layout).

`json` is imported inside the functions, not at module level, on purpose: see the
"Brython gotchas" note in CLAUDE.md (repeat page loads crash on Chrome/Chromium 154).
"""
from browser import ajax, document, html, window


def api_url():
    return document.body.attrs["data-api-url"].rstrip("/")


def show_toast(message, is_error=False):
    bg_class = "bg-rose-50 border-rose-200 text-rose-800" if is_error else "bg-emerald-50 border-emerald-200 text-emerald-800"
    icon_name = "ph-warning-circle" if is_error else "ph-check-circle"
    toast = html.DIV(
        html.DIV(
            [
                html.I(Class=f"ph {icon_name} text-xl mr-2 font-bold"),
                html.SPAN(message, Class="text-sm font-medium"),
            ],
            Class=f"flex items-center p-4 rounded-xl border shadow-lg backdrop-blur-md {bg_class}",
        ),
        Class="mb-3 pointer-events-auto",
    )
    document["toast_container"] <= toast

    def remove_toast():
        try:
            toast.remove()
        except Exception:
            pass

    window.setTimeout(remove_toast, 5000 if is_error else 3500)


def error_detail(req):
    """Best-effort human-readable message from a failed ajax request."""
    import json

    try:
        detail = json.loads(req.text).get("detail")
        if isinstance(detail, str):
            return detail
        if detail:
            return json.dumps(detail, ensure_ascii=False)
    except Exception:
        pass
    return f"HTTP {req.status}" if req.status else "ติดต่อ API ไม่ได้"


def request(method, path, on_ok, data=None, on_error=None, timeout=30):
    """Call the API. on_ok receives the parsed JSON body; errors default to a toast. `timeout` is in seconds."""

    import json

    def done(req):
        if req.status == 200:
            on_ok(json.loads(req.text) if req.text else None)
        elif on_error:
            on_error(req)
        else:
            show_toast(error_detail(req), True)

    fn = getattr(ajax, method)
    kwargs = {"oncomplete": done, "timeout": timeout}
    if method == "get":
        # Brython would append "?<timestamp>" itself, which breaks URLs that already have
        # a query string. Cache-bust with a proper param instead.
        path += ("&" if "?" in path else "?") + "_=" + str(window.Date.now())
        kwargs["cache"] = True
    if data is not None:
        kwargs["data"] = json.dumps(data)
        kwargs["headers"] = {"Content-Type": "application/json"}
    fn(api_url() + path, **kwargs)
