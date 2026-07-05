FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY pyproject.toml ./
RUN pip install -e . || pip install fastapi "uvicorn[standard]" pydantic pydantic-settings \
    "sqlalchemy[asyncio]" asyncpg redis httpx websockets cryptography python-jose argon2-cffi loguru
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
