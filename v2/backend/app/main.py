from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import settings
from .diagnostics import report

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
async def health(port: int | None = None):
    """Readiness of every external dependency. Never returns a secret value."""
    return await report(port)
