#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PY_TAG="${PY_TAG:-cp311-cp311}"
IMAGE_TAG="eigenpuls-pyinstaller:${PY_TAG}"
OUT_DIR_HOST="${REPO_ROOT}/dist"
SPEC_FILE="eigenpuls-client.spec"

mkdir -p "${OUT_DIR_HOST}"

echo "[1/3] Building builder image (${IMAGE_TAG})"
docker build \
  -f "${REPO_ROOT}/build/pyinstaller.manylinux.Dockerfile" \
  --build-arg PY_TAG="${PY_TAG}" \
  -t "${IMAGE_TAG}" \
  "${REPO_ROOT}"

echo "[2/3] Installing project inside container"
docker run --rm \
  -v "${REPO_ROOT}:/src" \
  -w /src \
  "${IMAGE_TAG}" \
  "python -m pip install -U . && python -m pip install -U pyinstaller"

echo "[3/3] Building binary via PyInstaller (${SPEC_FILE})"
docker run --rm \
  -v "${REPO_ROOT}:/src" \
  -w /src \
  "${IMAGE_TAG}" \
  "pyinstaller --clean -y ${SPEC_FILE}"

echo "Done. Artifacts in dist/"

