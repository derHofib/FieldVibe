FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r app && useradd -r -g app -d /app -m app
WORKDIR /app

COPY requirements.txt ./

# Test/CI-Stage: installiert zusaetzlich Dev-Abhaengigkeiten (pytest, moto, ...)
# und kopiert auch tests/ -- wird NIE als Produktions-Image verwendet, nur
# lokal bzw. fuer eine spaetere CI-Pipeline per `docker build --target deps`.
FROM base AS deps
COPY requirements-dev.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && pip install --no-cache-dir -r requirements-dev.txt \
    && apt-get purge -y gcc libpq-dev && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
COPY --chown=app:app . .
USER app

# Produktions-Stage (Default-Target, siehe docker-compose.yml): installiert
# nur Laufzeit-Abhaengigkeiten aus requirements.txt und kopiert weder tests/
# noch requirements-dev.txt -- dev-only Pakete wie moto (Fake-AWS-Server)
# gehoeren nicht ins Produktions-Image.
FROM base AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc libpq-dev && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Nur fuer die rein informative Update-Anzeige im Super-Admin-Bereich
# (siehe app/services/version_service.py) -- kein Docker-Socket/SSH-Zugriff,
# das Backend fuehrt daraus keine Aktualisierung selbst aus.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
