from .chat import blueprint as chat_bp
from .admin import blueprint as admin_bp
from .assessment import blueprint as assessment_bp

__all__ = ["chat_bp", "admin_bp", "assessment_bp"]
