# v2's API only. Vercel serves the interface and forwards /api here, so nothing
# in this image builds or ships the front end and there is no Node in it.
#
# Differences from v1's image, all deliberate:
#   * No gcc or postgresql-client. v2 talks to Firestore, not Postgres, and its
#     dependencies ship wheels, so nothing compiles at build time.
#   * The port comes from the environment. Render assigns $PORT and a hardcoded
#     one is ignored at best.
#   * No HEALTHCHECK on a fixed port for the same reason. /api/health exists and
#     makes a live model call, so it is a readiness report for a human rather
#     than something to poll every thirty seconds.

FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Requirements first, so a code change does not reinstall the dependency layer.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Shell form, so $PORT is expanded at run time rather than passed literally.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
