FROM python:3.15-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY main.py ./
RUN uv sync --frozen --no-dev

# The default SQLite file (db.sqlite3) lives in /app, so the app user must be able to write there.
RUN useradd --create-home appuser && chown appuser /app
USER appuser

# Railway sets PORT; the entrypoint (app.main:app) comes from [tool.fastapi] in pyproject.toml.
CMD ["sh", "-c", "fastapi run --host 0.0.0.0 --port ${PORT:-8000}"]
