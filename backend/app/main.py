from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.paths import ensure_data_dirs
from app.db import Base, engine, ensure_schema
from app.routers import (
    activity,
    chat,
    documents,
    health,
    keypoints,
    knowledge_bases,
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

    app.include_router(health.router, prefix="/api")
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
    app.include_router(progress.router, prefix="/api")

    return app


app = create_app()
