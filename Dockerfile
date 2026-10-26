# syntax=docker/dockerfile:1

# ---- 1. Build the React frontend ----
FROM node:22.11-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python API that also serves the built frontend ----
FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FRONTEND_DIST=/app/frontend/dist

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=frontend /build/dist /app/frontend/dist

RUN sed -i 's/\r$//' start.sh && chmod +x start.sh \
 && useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
CMD ["./start.sh"]
