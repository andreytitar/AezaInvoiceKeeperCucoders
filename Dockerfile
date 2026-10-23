# syntax=docker/dockerfile:1

# ---------- 1. Сборка SPA ----------
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. Runtime бэкенда (api и worker) ----------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ /app/
COPY --from=frontend /fe/dist /app/static
RUN useradd --uid 10001 --create-home app \
    && mkdir -p /app/uploads \
    && chown -R app /app/uploads \
    && chmod +x /app/docker-entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["api"]

# ---------- 3. Образ для тестов ----------
FROM runtime AS test
USER root
COPY backend/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
USER app
CMD ["test"]
