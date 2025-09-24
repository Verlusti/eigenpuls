# syntax=docker/dockerfile:1.7-labs

ARG PYTHON_VERSION=3.11
ARG DEBIAN_FRONTEND=noninteractive

############################
# Build stage
############################
FROM python:${PYTHON_VERSION}-bookworm AS build

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY eigenpuls /app/eigenpuls
# Copy default config if present in build context
COPY eigenpuls.yaml /app/eigenpuls.yaml

RUN pip install --upgrade pip && pip install --no-cache-dir .

# Emit required apt package names based on config copied into the image
# Overridable via --build-arg CONFIG_PATH=/path/in/image
ARG CONFIG_PATH=/app/eigenpuls.yaml
RUN if [ -f "${CONFIG_PATH}" ]; then \
      EIGENPULS_CONFIG=${CONFIG_PATH} python -m eigenpuls packages --type apt > /app/.apt-packages.txt; \
    else \
      echo "" > /app/.apt-packages.txt; \
    fi

    
############################
# Final stage
############################
FROM python:${PYTHON_VERSION}-slim-bookworm AS final

ARG DEBIAN_FRONTEND=noninteractive

# Install runtime deps and dynamically discovered apt packages
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python deps and app from builder
COPY --from=build /usr/local /usr/local
COPY --from=build /app /app

# If apt package list exists and is non-empty, install
RUN set -eux; \
    if [ -s /app/.apt-packages.txt ]; then \
      pkgs=$(cat /app/.apt-packages.txt); \
      apt-get update; \
      if [ -n "$pkgs" ]; then apt-get install -y --no-install-recommends $pkgs; fi; \
      rm -rf /var/lib/apt/lists/*; \
    fi

ENV EIGENPULS_CONFIG=/app/eigenpuls.yaml
EXPOSE 4242
CMD ["python", "-m", "eigenpuls", "serve", "-c", "/app/eigenpuls.yaml"]


