# JSAN Places Intelligence

A SEA Places POC workspace with an overview, persistent HERE customer datasets, and an AOI Viewer. React + MapLibre frontend, FastAPI backend, and PostgreSQL with PostGIS. Deployable to Railway as a single app service connected to a PostGIS database.

## Customer baseline workspace

- `/`: POC overview with live saved-dataset counts and three assigned areas.
- `/customer-data`: upload UTF-8 CSV or Excel `.xlsx` files, select the AOI, and browse saved records. Search by name/ID/address, filter categories, paginate, inspect complete records, or show every source column.
- `/aoi-viewer`: the existing boundary/place viewer. **View in AOI Viewer** on a saved dataset retrieves its persisted points from the API.

Configure `DATABASE_URL` in `backend/.env`, install backend requirements, and run `python -m alembic upgrade head` from `backend/`. The database server must have PostGIS available; the migration enables it and creates `customer_datasets` and `customer_pois` with spatial indexes. Docker Compose uses a PostGIS image. Existing remote plain-Postgres services must enable/install PostGIS or use a PostGIS-capable service first.

Imports are atomic: invalid IDs, duplicate IDs within a dataset, incomplete/out-of-range coordinates, or country/AOI mismatches reject the whole file with row-level errors. Identical file bytes for the same AOI are rejected as duplicates. Changed files create new dataset versions and do not overwrite prior imports; dashboard totals count all saved versions. Each file is limited to 25 MB / 100,000 populated records. For XLSX, all visible sheets must be POI tables; save legacy `.xls` as `.xlsx` first.

Every original column is retained in JSONB alongside normalized identity, category, address and coordinate columns. Display and optional routing locations are stored as `geometry(Point,4326)` with GiST indexes. Import validation checks coordinate ranges and assigned country; polygon containment, evidence verification, matching and delivery QC belong to the next POC phase. No external map collection is implemented in this change.

Customer API: `GET /api/customer-data/datasets`, `POST /api/customer-data/imports` (multipart `aoi` + `file`), `GET /api/customer-data/datasets/{id}/records` (`q`, `category`, `page`, `page_size`), and `GET /api/customer-data/datasets/{id}/geojson`.

For a scripted local import, run `python import_customer_files.py --aoi "Divisoria" "path/to/baseline.csv"` from `backend/` with development dependencies installed. Original uploads stay unchanged on disk. Data access uses the application's existing access model; authentication/roles are not added here.

```
frontend/          React + Vite app (map viewer)
backend/           FastAPI app: /api/* plus serving the built frontend
  app/main.py        app, SPA serving, gzip, CORS
  app/config.py      settings from environment variables
  app/db.py          SQLAlchemy engine/session (enabled when DATABASE_URL is set)
  app/api/           Health and customer-data API routers
  app/models/        Customer dataset and POI ORM models
  app/services/      CSV/XLSX parsing and row validation
  migrations/        Alembic baseline + PostGIS customer-data schema
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
4. Attach a PostGIS-enabled PostgreSQL service in the same project, then set the app's `DATABASE_URL` to that service's connection URL (use its actual service name for a Railway variable reference).
   On the next deploy `start.sh` runs `alembic upgrade head` before starting the server, and `/api/health` reports `"database": "ok"`.

Railway sets `PORT`; nothing else is required. Optional variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres connection (`postgres://` or `postgresql://` both work). |
| `ENVIRONMENT` | Free-form label shown in `/api/health`, e.g. `production`. |
| `CORS_ORIGINS` | Comma-separated origins, only if the frontend is hosted on another domain. |

> PostGIS is required for Customer Data. Migration `0002` creates the extension and spatial tables; the server must have the extension package installed.

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
