from fastapi import APIRouter
from .models import router as models_router
from .chat import router as chat_router

api_router = APIRouter()
api_router.include_router(models_router)
api_router.include_router(chat_router)

__all__ = ["api_router"]
