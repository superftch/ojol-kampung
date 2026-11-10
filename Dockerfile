FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-liberation fonts-noto-color-emoji ca-certificates gosu && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.6 && useradd -m -u 1000 app && mkdir -p /data/runtime && chown -R app:app /data
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY main.py ./
COPY ojol ./ojol
COPY docker/entrypoint.sh /usr/local/bin/ojol-entrypoint
RUN chmod 755 /usr/local/bin/ojol-entrypoint
ENV PATH="/app/.venv/bin:$PATH" OJOL_CONFIG_FILE=/data/config.env OJOL_RUNTIME_DIR=/data/runtime OJOL_MANAGED_BROWSER=true
EXPOSE 6080
ENTRYPOINT ["ojol-entrypoint"]
CMD ["python", "-m", "ojol.control"]

FROM runtime AS test
COPY tests ./tests
COPY scripts/test.py ./scripts/test.py
RUN uv sync --frozen && python scripts/test.py --prepare
RUN uv run ruff check . && uv run ruff format --check . && python scripts/test.py
