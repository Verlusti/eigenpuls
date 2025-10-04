ARG PYTHON_VERSION=3.11
ARG DEBIAN_FRONTEND=noninteractive

FROM python:${PYTHON_VERSION}-slim-bookworm

WORKDIR /app

# Install required system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md /app/
COPY eigenpuls /app/eigenpuls

# Install app
RUN pip install --upgrade pip && pip install --no-cache-dir .

# Start app
EXPOSE 4242
CMD ["python", "-m", "eigenpuls", "serve"]


