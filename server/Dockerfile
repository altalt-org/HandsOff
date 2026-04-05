FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    android-tools-adb curl \
    && rm -rf /var/lib/apt/lists/*

# Install apkeep for downloading APKs from APKPure / F-Droid
ARG TARGETARCH
ARG APKEEP_VERSION=0.18.0
RUN case "${TARGETARCH}" in \
        arm64) APKEEP_ARCH="aarch64-unknown-linux-gnu" ;; \
        amd64) APKEEP_ARCH="x86_64-unknown-linux-gnu" ;; \
        *) echo "Unsupported arch: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL "https://github.com/EFForg/apkeep/releases/download/${APKEEP_VERSION}/apkeep-${APKEEP_ARCH}" \
        -o /usr/local/bin/apkeep && \
    chmod +x /usr/local/bin/apkeep

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

# Create virtual environment
RUN uv venv /app/.venv
ENV VIRTUAL_ENV="/app/.venv"
ENV PATH="/app/.venv/bin:$PATH"

# Install droidrun-pkg (local dependency)
COPY droidrun-pkg /droidrun-pkg
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install /droidrun-pkg

# Install server dependencies (cached layer — only re-runs when pyproject.toml changes)
COPY server/pyproject.toml /tmp/server-deps/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r /tmp/server-deps/pyproject.toml

# Copy server code
COPY server/ ./server/

EXPOSE 8000

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
