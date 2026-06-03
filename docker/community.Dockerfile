FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY services ./services
RUN pip install --no-cache-dir -e .
CMD ["uvicorn", "community_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
