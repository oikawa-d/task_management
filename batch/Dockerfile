FROM python:3.14-slim AS builder
WORKDIR /build
COPY batch/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd -m -u 10001 appuser
COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser batch/app ./app
USER appuser
HEALTHCHECK CMD python -c "import os; os.kill(1, 0)"
CMD ["python", "-m", "app.main"]
