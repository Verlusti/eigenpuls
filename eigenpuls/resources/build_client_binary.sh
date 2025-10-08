#!/usr/bin/env bash
set -euo pipefail

# This script is intended to run INSIDE the manylinux container.
# It expects (by default) resources and output relative to the container CWD.
# You may override via environment variables.
#
# Defaults:
# - SPEC_PATH: ./eigenpuls-client.spec
# - OUT_DIR:   ./dist

OUT_DIR="${OUT_DIR:-/work/dist}"
SPEC_PATH="${SPEC_PATH:-/res/eigenpuls-client.spec}"

# Pick an available Python (prefer 3.11, else default)
PY_CANDIDATES=(
  "/opt/python/cp311-cp311/bin/python"
  "/opt/python311/bin/python"
  "$(command -v python3 || true)"
  "$(command -v python || true)"
)
PY=""
for p in "${PY_CANDIDATES[@]}"; do
  if [[ -n "$p" && -x "$p" ]]; then PY="$p"; break; fi
done
if [[ -z "$PY" ]]; then
  echo "No suitable python interpreter found" >&2
  exit 1
fi

# Compute lib dir relative to python prefix
PY_PREFIX_DIR="$($PY -c 'import sys,sysconfig,os; print(os.path.dirname(os.path.dirname(sys.executable)))')"
export LD_LIBRARY_PATH="${PY_PREFIX_DIR}/lib:${LD_LIBRARY_PATH:-}"

echo "[container] Installing build tooling (using ${PY})"
"${PY}" -m pip install -U pip pyinstaller

if [[ -n "${EIGENPULS_VERSION:-}" ]]; then
  echo "[container] Installing eigenpuls==${EIGENPULS_VERSION} (client only)"
  if ! "${PY}" -m pip install "eigenpuls==${EIGENPULS_VERSION}"; then
    echo "[container] Fallback: installing latest eigenpuls"
    "${PY}" -m pip install "eigenpuls"
  fi
else
  echo "[container] Installing latest eigenpuls"
  "${PY}" -m pip install "eigenpuls"
fi

SITE_PKGS=$("${PY}" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')

mkdir -p /tmp/build /work
cd /tmp/build

# Expose installed package as a local folder for spec path resolution
if [[ ! -e eigenpuls ]]; then
  ln -s "${SITE_PKGS}/eigenpuls" eigenpuls
fi

mkdir -p "${OUT_DIR}"

# Use a local copy of the spec so relative paths resolve against /tmp/build
SPEC_LOCAL="/tmp/build/eigenpuls-client.spec"
cp "${SPEC_PATH}" "${SPEC_LOCAL}"
SPEC_PATH="${SPEC_LOCAL}"

echo "[container] Building with PyInstaller via ${PY}"
"${PY}" -m PyInstaller --clean -y --distpath "${OUT_DIR}" "${SPEC_PATH}"

echo "[container] Build complete; artifacts in ${OUT_DIR}"

