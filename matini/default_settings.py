import os
from dotenv import load_dotenv

load_dotenv()

APP_TITLE = "Matini"
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_URL = os.getenv("API_URL", f"http://{API_HOST}:{API_PORT}")

WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
DEBUG = os.getenv("DEBUG", "true").lower() in ("true", "1", "t")
SECRET_KEY = os.getenv("SECRET_KEY", "matini-secret-key-super-secure-dev")
