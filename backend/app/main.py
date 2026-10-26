from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from .api import api_router
from .config import get_settings

settings = get_settings()

app = FastAPI(
    title=f"{settings.app_name} API",
    version=settings.version,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix="/api")


# ---------- Frontend (built React app) ----------
DIST: Path = settings.frontend_dist.resolve()
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}  # Vite hashes asset file names
NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str) -> FileResponse:
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    index = DIST / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Frontend not built. Run `npm run build` in frontend/.")
    if path:
        file = (DIST / path).resolve()
        if file.is_relative_to(DIST) and file.is_file():
            return FileResponse(file, headers=IMMUTABLE if path.startswith("assets/") else NO_CACHE)
    # Client-side routes fall back to the SPA shell.
    return FileResponse(index, headers=NO_CACHE)
