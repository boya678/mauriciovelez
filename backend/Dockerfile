# ── Stage 1: dependencias ─────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Instalar solo dependencias (cacheable)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: imagen final ─────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copiar paquetes instalados
COPY --from=builder /install /usr/local

# Copiar código fuente y migraciones
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Usuario sin privilegios
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

EXPOSE 8000

# Ejecutar migraciones y levantar la app
CMD alembic upgrade head && \
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
