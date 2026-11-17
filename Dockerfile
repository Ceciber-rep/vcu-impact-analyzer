# VCU-42 change impact analyzer: Streamlit app.
#   docker build -t vcu-impact .
#   docker run --rm -p 8501:8501 vcu-impact                  # replay mode, no key needed
#   docker run --rm -p 8501:8501 --env-file .env vcu-impact  # with a live model
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

# Dependencies first, for layer caching.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code and data (no secrets: .env is excluded by .dockerignore).
COPY src ./src
COPY app ./app
COPY data ./data
COPY docs/known_issues.md ./docs/known_issues.md
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

# Run as an unprivileged user; the local analysis cache lives in /app/.cache.
RUN useradd --create-home appuser && mkdir -p /app/.cache && chown -R appuser /app/.cache
USER appuser

CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
