from flask import Blueprint, render_template

blueprint = Blueprint("chat", __name__)


@blueprint.route("/")
@blueprint.route("/c/<conversation_id>")
def index(conversation_id: str = ""):
    # Conversations, LLMs and streaming are all loaded client-side (Brython) from the API.
    return render_template("chat/index.html", conversation_id=conversation_id)
