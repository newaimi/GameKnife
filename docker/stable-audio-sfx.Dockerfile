FROM python:3.12-slim

WORKDIR /app
COPY services-extra/stable-audio-sfx/pyproject.toml ./pyproject.toml
COPY services-extra/stable-audio-sfx/app ./app
RUN pip install --no-cache-dir -e .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
