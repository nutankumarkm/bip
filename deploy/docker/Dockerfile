FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini ./

RUN pip install --no-cache-dir -e .

EXPOSE 8080 8081

CMD ["python", "-m", "uvicorn", "bip.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
