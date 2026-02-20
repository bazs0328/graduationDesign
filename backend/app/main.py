from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.auth import (
    extract_bearer_token,
    reset_request_user_id,
    set_request_user_id,
    verify_access_token,
)
from app.core.config import settings
from app.core.paths import ensure_data_dirs
from app.db import Base, engine, ensure_schema
from app.routers import (
    activity,
    auth,
    chat,
    documents,
    health,
    keypoints,
    knowledge_bases,
    learning_path,
    progress,
    qa,
    quiz,
    profile,
    recommendations,
    summary,
)


def create_app() -> FastAPI:
    ensure_data_dirs()
    Base.metadata.create_all(bind=engine)
    ensure_schema()

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def auth_context_middleware(request: Request, call_next):
        request_user_id: str | None = None
        token = extract_bearer_token(request.headers.get("Authorization"))
        if token:
            request_user_id = verify_access_token(token)
            if not request_user_id:
                return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

        is_api_path = request.url.path.startswith("/api")
        is_public_path = request.url.path.startswith("/api/auth") or request.url.path.startswith(
            "/api/health"
        )
        if (
            request.method != "OPTIONS"
            and is_api_path
            and not is_public_path
            and settings.auth_require_login
            and not request_user_id
            and not settings.auth_allow_legacy_user_id
        ):
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

        token_ctx = set_request_user_id(request_user_id)
        try:
            return await call_next(request)
        finally:
            reset_request_user_id(token_ctx)

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(activity.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(knowledge_bases.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(summary.router, prefix="/api")
    app.include_router(keypoints.router, prefix="/api")
    app.include_router(qa.router, prefix="/api")
    app.include_router(quiz.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(recommendations.router, prefix="/api")
    app.include_router(learning_path.router, prefix="/api")
    app.include_router(progress.router, prefix="/api")

    return app


app = create_app()
