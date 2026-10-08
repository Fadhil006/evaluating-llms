FROM node:24-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=data/lab.sqlite3 \
    DEMO_DATABASE_PATH=data/demo.sqlite3
WORKDIR /app/backend
COPY backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock \
    && pip uninstall -y pytest ruff iniconfig packaging pluggy pygments \
    && rm /tmp/requirements.lock
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY datasets /app/datasets
RUN pip install --no-cache-dir --no-deps .
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist
RUN mkdir -p /app/data
EXPOSE 8000
