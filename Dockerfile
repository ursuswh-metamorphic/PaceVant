# Build Solidity once with native Foundry. No Node.js/npm in any stage.
FROM ghcr.io/foundry-rs/foundry:v1.7.1 AS foundry

FROM python:3.12-slim-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=foundry /usr/local/bin/forge /usr/local/bin/forge
COPY --from=foundry /usr/local/bin/anvil /usr/local/bin/anvil
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.10
COPY pyproject.toml uv.lock .python-version ./
COPY packages/contracts-api packages/contracts-api
COPY apps/control-plane apps/control-plane
COPY apps/execution-plane apps/execution-plane
COPY apps/dashboard apps/dashboard
COPY scripts scripts
COPY contracts contracts
COPY fixtures fixtures
COPY foundry.toml ./
RUN uv sync --locked --no-dev --python /usr/local/bin/python \
    && uv sync --project apps/execution-plane --locked --no-dev --python /usr/local/bin/python
RUN /app/.venv/bin/python scripts/bootstrap.py && /app/.venv/bin/python scripts/foundry.py forge build

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app /app
COPY --from=foundry /usr/local/bin/anvil /usr/local/bin/anvil
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=10000 \
    TREASURY_SERVER_DATA_DIR=/var/data
EXPOSE 10000
STOPSIGNAL SIGTERM
CMD ["python", "scripts/container.py"]
