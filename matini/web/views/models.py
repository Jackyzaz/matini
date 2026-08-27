import requests
from flask import Blueprint, render_template, current_app, abort
from matini.api.services.registry import get_model_by_id

blueprint = Blueprint("models", __name__, url_prefix="/model")

@blueprint.route("/<model_id>")
def detail(model_id: str):
    api_url = current_app.config.get("API_URL", "http://127.0.0.1:8000")
    model_data = None
    try:
        res = requests.get(f"{api_url}/api/models/{model_id}", timeout=2)
        if res.status_code == 200:
            model_data = res.json()
    except Exception:
        pass
    
    if not model_data:
        m = get_model_by_id(model_id)
        if not m:
            abort(404)
        model_data = m.model_dump()

    return render_template("models/detail.html", model=model_data, api_url=api_url)
