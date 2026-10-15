
# Use a slim Python base image
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Configure Python and uv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Create a non-root user
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# Install locked production dependencies first for better build caching
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy application files with correct ownership
COPY --chown=appuser:appuser app ./app

# Install the project and create a writable data directory
RUN uv sync --frozen --no-dev \
    && mkdir -p /app/app/data \
    && chown appuser:appuser /app/app/data

# Run as a non-root user
USER appuser

EXPOSE 8000

# Container health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# Start the API
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
