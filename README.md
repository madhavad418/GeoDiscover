# JSAN Places Intelligence

A SEA Places POC workspace with an overview, persistent HERE customer datasets, and an AOI Viewer. React + MapLibre frontend, FastAPI backend, and PostgreSQL with PostGIS. Deployable to Railway as a single app service connected to a PostGIS database.

## Customer baseline workspace

- `/`: POC overview with live saved-dataset counts and three assigned areas.
- `/customer-data`: upload UTF-8 CSV or Excel `.xlsx` files, select the AOI, and browse saved records. Search by name/ID/address, filter categories, paginate, inspect complete records, or show every source column.
- `/aoi-viewer`: the existing boundary/place viewer. **View in AOI Viewer** on a saved dataset retrieves its persisted points from the API.
- `/sources`, `/compare`, `/my-work`, `/tasks/:id`, `/delivery`, `/operations-dashboard`: the POI discovery, comparison, review/QC and delivery workflow (below).

Configure `DATABASE_URL` in `backend/.env`, install backend requirements, and run `python -m alembic upgrade head` from `backend/`. The database server must have PostGIS available; the migrations enable it, create `customer_datasets` and `customer_pois` with spatial indexes, and add persistent provider-comparison review decisions. Docker Compose uses a PostGIS image. Existing remote plain-Postgres services must enable/install PostGIS or use a PostGIS-capable service first.

Imports are atomic: invalid IDs, duplicate IDs within a dataset, incomplete/out-of-range coordinates, or country/AOI mismatches reject the whole file with row-level errors. Identical file bytes for the same AOI are rejected as duplicates. Changed files create new dataset versions and do not overwrite prior imports; dashboard totals count all saved versions. Each file is limited to 25 MB / 100,000 populated records. For XLSX, all visible sheets must be POI tables; save legacy `.xls` as `.xlsx` first.

Every original column is retained in JSONB alongside normalized identity, category, address and coordinate columns. Display and optional routing locations are stored as `geometry(Point,4326)` with GiST indexes. Import validation checks coordinate ranges and assigned country; polygon containment, evidence verification, matching and delivery QC belong to the next POC phase. No external map collection is implemented in this change.

Customer API: `GET /api/customer-data/datasets`, `POST /api/customer-data/imports` (multipart `aoi` + `file`), `GET /api/customer-data/datasets/{id}/records` (`q`, `category`, `page`, `page_size`), and `GET /api/customer-data/datasets/{id}/geojson`.

For a scripted local import, run `python import_customer_files.py --aoi "Divisoria" "path/to/baseline.csv"` from `backend/` with development dependencies installed. Original uploads stay unchanged on disk. The script acts as a local system Operations Manager.

```
frontend/          React + Vite app (map viewer)
backend/           FastAPI app: /api/* plus serving the built frontend
  app/main.py        app, SPA serving, gzip, CORS
  app/config.py      settings from environment variables
  app/db.py          SQLAlchemy engine/session (enabled when DATABASE_URL is set)
  app/api/           Auth, customer data, sources, comparison, tasks, delivery
  app/models/        Customer dataset and POI ORM models
  app/services/      Parsing, matching, review rules, workflow, delivery
  migrations/        Alembic baseline + PostGIS customer-data schema
  start.sh           container entrypoint: migrate, then run uvicorn
Dockerfile         multi-stage: build frontend, then Python runtime
railway.json       Railway build/deploy config (Dockerfile + /api/health check)
docker-compose.yml local app + Postgres
```

## POI discovery, comparison, review/QC & delivery

One workflow from permitted sources to the exact HERE templates (consolidated requirements §§1–10, Delivery Guide v1.2, Delete Framework v1.0, Evidence Workbook).

1. **Sign in.** Every API except `/api/health` and sign-in needs a session. Roles: Reviewer, QC Analyst, QC Lead, Field Verifier, Operations Manager; users can be limited to AOIs. Create the first Operations Manager from `backend/`:
   `python manage_users.py create --username ops.lead --name "Ops Lead" --roles ops_manager qc_lead` (password prompted). Further users: **Operations dashboard → Team & roles**.
2. **Import permitted sources** (`/sources`, Ops Manager / QC Lead): CSV/XLSX observations with a source record ID, name and coordinates, plus the batch's licence reference and permitted use. Rows outside the HERE AOI are skipped; rows pointing at map providers are rejected.
3. **Run the comparison.** Observations of the same business across sources are linked into one master POI (JSAN ID); chain branches, tenants sharing a coordinate and same-source records are never merged. Each master is matched to HERE with the Delete Framework identity signals (M1 name ≥ 0.85 token-set, M2 category L2, M3 phone, M4 address, M5 website/social; chain brands need a unit-level signal) and bands B0 ≤ 50 m, B1 ≤ 250 m, B2 ≤ 1 km, B3 identity-led. Outcomes: MATCHED/NO CHANGE, POTENTIAL UPDATE, POTENTIAL NEW, VERIFICATION REQUIRED, POTENTIAL DELETE (only when a source reports closure), FALLOUT REVIEW. Every result explains its signals, differences and other candidates. Unchanged inputs reuse the previous run.
4. **Generate tasks.** Source-backed findings by default; verification tasks for HERE POIs no source observed are a separate action. Keys include the finding's content, so re-runs never duplicate tasks.
5. **My work → Get tasks.** Keeps in-progress work, then claims by role, AOI and priority (`FOR UPDATE SKIP LOCKED`, so no double assignment). Supervisors reassign from the Operations dashboard; every transition is in the task history.
6. **Review** in the task window: HERE record and nearby POIs, linked source records with licences, match signals, reference links (Google Maps / Street View / OSM open in their own viewers), and an attribute grid with proposed corrections. Decisions are rejected unless they carry the required evidence: NEW needs two independent evidence types incl. imagery/field/POS; each UPDATE change needs supporting evidence; DELETE needs E1 or ≥ 70 points from ≥ 2 closure tiers with no equal-or-higher liveness evidence (absence never counts).
7. **Independent QC** (QC user ≠ anyone who reviewed or field-verified the record): approve (rules re-checked), reject, return for rework, reclassify, request field verification, hold/escalate. Field results return to QC automatically.
8. **Delivery** (`/delivery`): only QC-approved records that pass the Blocker gates are written into copies of the three HERE templates (original sheet names, headers and order; text written as literals). Records with Blockers are withheld and listed; Major issues are disclosed. The package adds the manifest, QC checklist and category mapping; the reconciliation report is internal only. Snapshots are frozen with SHA-256 checksums.

**Source policy.** Google Places, Grab and Apple are reference-only: reviewers open them in their own viewers; their content is never imported, stored or exported (Delivery Guide p.7 licensing prerequisite; provider terms).

Reference data and templates are bundled in `backend/app/resources/`; rebuild them with `python build_reference_data.py "<POC Material folder>"` when HERE issues updates. Rules and open clarifications for HERE are listed on the **POC readiness** page.

Tests: `pytest` runs the matching, rule and end-to-end workflow tests on SQLite. `RUN_DATABASE_TESTS=1` runs the PostGIS storage tests; `TEST_DATABASE_URL=<disposable migrated database>` runs the concurrent-allocation test.

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
- **Places:** clustered and coloured by category. Click a point for identifier, category, address, containing boundary, contact details, opening hours and all attributes, plus **Open Street View** (Google Street View in a new tab at the routing point, else the display point). Use **Translate** to translate non-Latin text into English or **Transliterate** to show its pronunciation in Latin script; selected text is sent to Google's public translation service. Filter categories and pick the label field (e.g. `placeid`) in the layer card.
- Search (`/`), measure distance/area (`M`), zoom to all (`F`), labels (`L`), basemaps (`B`: Dark, Light, Streets, Satellite via Esri, no key needed), export GeoJSON, save PNG.


### POC Operations

Open `/poc-operations` for the source-package audit, exact template headers, provider diagnostics and saved PostGIS baseline checks. Run `python -m alembic upgrade head` to add the preflight report table (migration 0004). Configure Google Places and the AWS Grab named Place Index in `backend/.env`; secrets remain server-side. Provider tests make one bounded request and retain no POI records. They are restricted to the local operator workspace pending role-based login.

See [the final requirements assessment](docs/POC_FINAL_REQUIREMENTS_ASSESSMENT.md) for module status, architecture, processing rules and P0 acceptance criteria. Bulk discovery, real matching, independent review/QC, field workflow and gated customer exports are not yet implemented. The existing Compare screen uses demonstration proposals. Apple is not enabled. Source storage and delivery rights must be established separately.


### AOI Viewer: provider collection

Upload a supported polygon file, select an area, then choose **Collect POIs (APIs)**. Operations managers and QC leads can run Google Places Text Search (New) and AWS GrabMaps Places v2 SearchText. The dialog offers a per-provider request ceiling, grid size, language and optional custom search terms. Defaults use the supplied HERE reference category names as text queries; they do not represent complete provider taxonomy coverage. Google and Grab pagination are followed; capped cells are subdivided up to two levels, subject to budget. Exact polygon filtering includes holes and separate MultiPolygon parts. IDs are deduplicated separately for each provider.

The Excel file contains exactly `Google` and `Grab` sheets with the 35 source CSV columns. It downloads automatically when a run finishes with records, and can be downloaded again manually. Empty/failed providers still have a sheet; A1 comments record errors, caps and pending queries. IDs are provider IDs. Unavailable fields and unverified HERE category codes remain blank. Google address components map only unambiguous fields; administrative levels are not guessed. Grab v2 supplies Title, Address, Position and Categories; unavailable contact, routing and opening-hours fields remain blank. Attribution is retained in ID-cell comments. Exports are raw provider extracts, separate from the approved customer-delivery pipeline, and reuse remains subject to provider agreements.

API results are not exhaustive. Budget exhaustion, response caps and failures are explicitly reported. Google richer fields may use higher-priced SKUs. Grab uses `/v2/search-text`, with `NextToken` pagination and `IntendedUse=Storage` for Excel extracts; `GRAB_PLACE_INDEX` is not used. Credentials stay on the backend. Runs are owner-scoped, kept temporarily in process memory, expire one hour after completion and disappear on server restart. Use a **single backend worker** for this local POC; persistent queues and distributed job storage are required before scaling. One run can execute at a time. Cancellation retains completed results after the current request finishes. Collection accepts valid WGS84 Polygon/MultiPolygon shapes with a bounding box below 100 km?; split larger areas.
