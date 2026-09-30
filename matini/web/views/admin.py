from flask import Blueprint, render_template

blueprint = Blueprint("admin", __name__, url_prefix="/admin")


@blueprint.route("/")
def index():
    return render_template("admin/index.html")
