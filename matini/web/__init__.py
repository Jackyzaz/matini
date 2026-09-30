from flask import Flask
from matini import default_settings
from matini.web.views import chat_bp, admin_bp, assessment_bp

def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # Load configurations
    app.config.from_object(default_settings)

    # Register blueprints
    app.register_blueprint(chat_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(assessment_bp)

    @app.context_processor
    def inject_global_variables():
        return {
            "app_title": app.config.get("APP_TITLE", "Matini"),
            "api_url": app.config.get("API_URL", "http://127.0.0.1:8000"),
        }

    return app

__all__ = ["create_app"]
