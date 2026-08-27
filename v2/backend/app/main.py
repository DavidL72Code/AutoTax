from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import llm
from .api.routes import router
from .config import settings

# The root .env carries a multi-line service-account JSON that python-dotenv
# cannot parse; the values we need load fine, so drop the noise.
logging.getLogger("dotenv.main").setLevel(logging.ERROR)

app = FastAPI(title="Receipts", version="2.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": settings.gemini_model if llm.available() else None,
        "environment": settings.app_env,
    }
