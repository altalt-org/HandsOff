FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    android-tools-adb \
    default-jre-headless \
    apksigner \
    && rm -rf /var/lib/apt/lists/*

# APKEditor for merging split APKs + asset packs into a single installable APK
ADD https://github.com/REAndroid/APKEditor/releases/download/V1.4.8/APKEditor-1.4.8.jar /opt/apkeditor.jar

# Generate a signing key for re-signing merged APKs
RUN keytool -genkey -v -keystore /opt/sideload.keystore -storepass handsoff \
    -alias sideload -keypass handsoff -keyalg RSA -keysize 2048 -validity 36500 \
    -dname "CN=HandsOff,O=HandsOff" 2>/dev/null

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
