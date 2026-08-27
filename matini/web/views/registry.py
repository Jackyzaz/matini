import requests
from flask import Blueprint, render_template, current_app
from matini.api.services.registry import get_all_models

blueprint = Blueprint("registry", __name__)

@blueprint.route("/")
def index():
    api_url = current_app.config.get("API_URL", "http://127.0.0.1:8000")
    try:
        res = requests.get(f"{api_url}/api/models", timeout=2)
        if res.status_code == 200:
            models = res.json()
        else:
            models = [m.model_dump() for m in get_all_models()]
    except Exception:
        # Fallback to direct service call if API service is initializing
        models = [m.model_dump() for m in get_all_models()]
        
    return render_template("registry/index.html", models=models, api_url=api_url)
