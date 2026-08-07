# Uses uv's documented Docker pattern: install deps from the lockfile
# first (cached layer, only invalidated when deps change), then copy the
# actual app code and install the project itself.

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

# --- Dependency layer (cached unless pyproject.toml/uv.lock change) ---
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# --- App layer ---
COPY app ./app
RUN uv sync --frozen --no-dev

RUN mkdir -p /app/app/data && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
