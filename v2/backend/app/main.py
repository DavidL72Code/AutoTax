from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import BACKEND, settings
from .diagnostics import report

# The root .env carries a multi-line service-account JSON that python-dotenv
# cannot parse; the values we need load fine, so drop the noise.
logging.getLogger("dotenv.main").setLevel(logging.ERROR)

# The interactive docs enumerate every route, its parameters and its shapes.
# That is exactly what you want while building and a free map of the attack
# surface once it is public, so they exist in development only.
_docs = settings.app_env == "development"

app = FastAPI(
    title="Receipts",
    version="2.0.0",
    docs_url="/api/docs" if _docs else None,
    redoc_url="/api/redoc" if _docs else None,
    openapi_url="/api/openapi.json" if _docs else None,
)

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


# ── the front end ───────────────────────────────────────────────────────────
#
# `next build` with `output: "export"` turns the whole interface into static
# HTML and JavaScript that calls `/api/...` relatively. Serving it from here
# makes the app one origin and one deployment: no second host, no CORS, and the
# session cookie works because there is nothing cross-site about it.
#
# Absent (a backend-only dev run, or before the front end is built) the API just
# serves itself.

# Anchored to the backend directory rather than counted from this file, for the
# same reason config.py is: in the image only v2/backend is copied, so the
# parents this used to count do not exist. There the export is absent and the
# guard below simply skips, which is correct when Vercel serves the pages.
FRONTEND = BACKEND.parent / "frontend" / "out"


def _page(path: str) -> Path | None:
    """Map a URL to an exported file. `next export` writes `dashboard.html`,
    not `dashboard/index.html`, so a plain StaticFiles mount misses every route
    but the root."""
    clean = path.strip("/")
    if not clean:
        candidate = FRONTEND / "index.html"
        return candidate if candidate.is_file() else None
    for candidate in (FRONTEND / f"{clean}.html", FRONTEND / clean / "index.html"):
        if candidate.is_file():
            return candidate
    return None


if FRONTEND.is_dir():
    app.mount("/_next", StaticFiles(directory=FRONTEND / "_next"), name="next-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        # Anything under /api that reached here is a real 404, not a page.
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such endpoint")

        page = _page(path)
        if page:
            return FileResponse(page)

        asset = FRONTEND / path
        if path and asset.is_file():
            return FileResponse(asset)

        not_found = FRONTEND / "404.html"
        if not_found.is_file():
            return FileResponse(not_found, status_code=404)
        raise HTTPException(status_code=404, detail="Not found")
