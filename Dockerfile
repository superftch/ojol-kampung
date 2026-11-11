FROM cloudflare/cloudflared:2026.10.7@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba AS tunnel
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates gosu && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 app
WORKDIR /app
COPY --from=tunnel /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.11.6 && UV_PYTHON_DOWNLOADS=never uv sync --frozen --no-dev --no-cache && pip uninstall -y uv
COPY main.py ./
COPY ojol ./ojol
COPY docker/entrypoint.sh /usr/local/bin/ojol-entrypoint
# Checkout permissions may be 600/700; the runtime switches to UID 1000.
RUN chmod -R a+rX /app/ojol && chmod 644 /app/main.py /app/pyproject.toml /app/uv.lock && chmod 755 /usr/local/bin/ojol-entrypoint
ENV PATH="/app/.venv/bin:$PATH" OJOL_CONFIG_FILE=/data/config.env OJOL_RUNTIME_DIR=/data/runtime
EXPOSE 6080
ENTRYPOINT ["ojol-entrypoint"]
CMD ["python", "-m", "ojol.control"]

FROM runtime AS test
ENV UV_PYTHON_DOWNLOADS=never
COPY tests ./tests
COPY scripts/test.py ./scripts/test.py
RUN pip install --no-cache-dir uv==0.11.6 && uv sync --frozen --no-cache && python scripts/test.py --prepare && chmod -R a+rX tests scripts && mkdir -p .local/testing && chown -R app:app .local .env.testing
RUN uv run ruff check . && uv run ruff format --check . && gosu app python scripts/test.py -o cache_dir=/app/.local/testing/pytest-cache
