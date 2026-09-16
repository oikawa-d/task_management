FROM python:3.14-slim AS builder
WORKDIR /build
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=builder /install /usr/local
RUN useradd -m -u 10001 appuser
WORKDIR /app/api
COPY --chown=appuser:appuser api/app ./app
COPY --chown=appuser:appuser api/alembic ./alembic
COPY --chown=appuser:appuser api/alembic.ini ./alembic.ini
COPY --chown=appuser:appuser api/entrypoint.sh ./entrypoint.sh
COPY --chown=appuser:appuser db /app/db
RUN chmod +x entrypoint.sh
USER appuser
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
ENTRYPOINT ["./entrypoint.sh"]
