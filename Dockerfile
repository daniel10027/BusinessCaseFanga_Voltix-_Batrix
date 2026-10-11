FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8000 9000

CMD ["uvicorn", "fanga_ingest.main:app", "--host", "0.0.0.0", "--port", "8000"]
