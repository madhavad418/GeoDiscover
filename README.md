# GeoDiscover: AOI Viewer

A map viewer for area-of-interest boundaries and place extracts. React + MapLibre frontend, FastAPI backend, PostgreSQL-ready, deployable to Railway as a single service.

```
frontend/          React + Vite app (map viewer)
backend/           FastAPI app: /api/* plus serving the built frontend
  app/main.py        app, SPA serving, gzip, CORS
  app/config.py      settings from environment variables
  app/db.py          SQLAlchemy engine/session (enabled when DATABASE_URL is set)
  app/api/           API routers (health.py so far)
  app/models/        ORM models (none yet)
  migrations/        Alembic migrations (baseline 0001 is empty)
  start.sh           container entrypoint: migrate, then run uvicorn
Dockerfile         multi-stage: build frontend, then Python runtime
railway.json       Railway build/deploy config (Dockerfile + /api/health check)
docker-compose.yml local app + Postgres
```

## Local development

Two terminals:

```bash
# 1. API on http://localhost:8000
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements-dev.txt
cp .env.example .env              # optional: set DATABASE_URL
uvicorn app.main:app --reload

# 2. Frontend on http://localhost:5173 (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Tests: `cd backend && pytest`.

With Docker installed, `docker compose up --build` runs the production image with a local Postgres at http://localhost:8000.

## Deploy to Railway

1. Push this repo to GitHub.
2. In Railway: **New Project → Deploy from GitHub repo** and pick it. Railway reads `railway.json`, builds the `Dockerfile`, and health-checks `/api/health`.
3. **Settings → Networking → Generate Domain** to get a public URL.
4. When the database is needed: **+ New → Database → PostgreSQL** in the same project, then on the app service add the variable
   `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`.
   On the next deploy `start.sh` runs `alembic upgrade head` before starting the server, and `/api/health` reports `"database": "ok"`.

Railway sets `PORT`; nothing else is required. Optional variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres connection (`postgres://` or `postgresql://` both work). |
| `ENVIRONMENT` | Free-form label shown in `/api/health`, e.g. `production`. |
| `CORS_ORIGINS` | Comma-separated origins, only if the frontend is hosted on another domain. |

> Need spatial queries? Use Railway's PostGIS template instead of plain PostgreSQL, then add `op.execute("CREATE EXTENSION IF NOT EXISTS postgis")` in a migration.

## Adding backend features

- **Endpoint:** create `backend/app/api/<name>.py` with an `APIRouter` and include it in `app/api/__init__.py`. Use `db: Session = Depends(get_db)` from `app.db` for database access. The frontend calls it as `fetch('/api/<name>')`, with no extra config in dev or production.
- **Table:** add a model in `backend/app/models/` (subclass `Base`, import it in `models/__init__.py`), then
  `alembic revision --autogenerate -m "add <table>"` (needs `DATABASE_URL`) and commit the new file in `migrations/versions/`.
- API docs: `/api/docs`.

## Using the viewer

Drag files onto the window, or use **Choose files**:

| Format | Notes |
| --- | --- |
| `.geojson` / `.json` | Boundaries, WGS84 (CRS84/EPSG:4326). EPSG:3857 is detected and reprojected. Point-only files load as places. |
| Shapefile `.zip` or `.shp` + `.dbf` + `.prj` | Boundaries, reprojected using the `.prj`. |
| `.qmd` | QGIS metadata; its CRS is attached to the layer with the same name. |
| `.csv` / `.tsv` | Places. Latitude/longitude columns are detected (`displaylatitude`, `latitude`, `lat`, …). |
| `.xlsx` / `.xls` | Places. Every sheet with latitude/longitude columns becomes a layer. |

Loading a file with the same name again replaces that layer.

- **Boundaries:** colour, opacity, distinct per-polygon colours, labels; click a polygon for admin hierarchy, local name, area, perimeter, P-code and attributes.
- **Places:** clustered and coloured by category. Click a point for identifier, category, address, containing boundary, contact details, opening hours and all attributes, plus **Open Street View** (Google Street View in a new tab at the routing point, else the display point). Filter categories and pick the label field (e.g. `placeid`) in the layer card.
- Search (`/`), measure distance/area (`M`), zoom to all (`F`), labels (`L`), basemaps (`B`: Dark, Light, Streets, Satellite via Esri, no key needed), export GeoJSON, save PNG.
