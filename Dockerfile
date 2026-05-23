FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY packages ./packages
COPY apps ./apps
COPY alembic.ini alembic ./alembic

RUN uv pip install --system -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

ENV PYTHONPATH=/app/packages/shared/src:/app/packages/connectors/src:/app/packages/llm/src:/app/packages/graph/src:/app/apps/api/src

EXPOSE 8000

CMD ["uvicorn", "ekcip_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
