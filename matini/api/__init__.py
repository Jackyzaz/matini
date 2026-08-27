from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from matini.api.core.config import settings
from matini.api.routers import api_router

def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Enable CORS for frontend and Brython requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": settings.app_title}

    return app

__all__ = ["create_application"]
