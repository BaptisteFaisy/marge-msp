#!/usr/bin/env bash
# Assemble the Lambda deployment package of Marge.
#
# One directory per function family, each holding the `marge` package, the
# static portal when the function serves it, and the runtime dependencies
# vendored in place (no layer, no Docker): Lambda unzips the directory at
# /var/task, so `import marge.lambdas.handlers` just works.
#
# The wheels are the ones of the Lambda runtime, whatever the machine that
# builds: pydantic-core is compiled, and a Windows or macOS wheel would not
# load on the Linux runtime of the function. The defaults below are the
# python3.12 runtime of `lambda_.Runtime.PYTHON_3_12`.
#
# Usage : scripts/build-lambda-package.sh [répertoire de sortie]
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/infra/cdk/.build}"
PORTAL_PKG="$OUT/portal"
JOBS_PKG="$OUT/jobs"

LAMBDA_PYTHON_VERSION="${LAMBDA_PYTHON_VERSION:-3.12}"
LAMBDA_PLATFORM="${LAMBDA_PLATFORM:-manylinux2014_x86_64}"
LAMBDA_IMPLEMENTATION="${LAMBDA_IMPLEMENTATION:-cp}"

# Dépendances d'exécution du portail (FastAPI + sa chaîne), stdlib ailleurs.
PORTAL_DEPS=(fastapi starlette pydantic pydantic-core annotated-types anyio sniffio idna typing-extensions)

build_package() { # $1 = destination, $2 = "with-portal|bare", reste = deps pip
  local dest="$1" mode="$2"; shift 2
  rm -rf "$dest"
  mkdir -p "$dest"
  cp -a "$ROOT/src/marge" "$dest/marge"
  if [ "$mode" = "with-portal" ]; then
    cp -a "$ROOT/portal" "$dest/portal"
  fi
  if [ "$#" -gt 0 ]; then
    python3 -m pip install --quiet --target "$dest" \
      --platform "$LAMBDA_PLATFORM" \
      --python-version "$LAMBDA_PYTHON_VERSION" \
      --implementation "$LAMBDA_IMPLEMENTATION" \
      --only-binary=:all: --upgrade "$@"
  fi
  find "$dest" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  find "$dest" -name '*.dist-info' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  printf '%-28s %s\n' "$(basename "$dest")" "$(du -sh "$dest" | cut -f1)"
}

mkdir -p "$OUT"
echo "== Paquets Lambda =="
build_package "$PORTAL_PKG" with-portal "${PORTAL_DEPS[@]}"
# Les jobs (nightly/weekly/monthly/publish) et les lecteurs de contrats
# n'utilisent que la stdlib + boto3, déjà fourni par le runtime Python.
build_package "$JOBS_PKG" bare

cat > "$OUT/MANIFEST.txt" <<EOF
marge lambda packages
built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
python=$(python3 -V 2>&1)
portal_handler=marge.lambdas.handlers.portal_handler
jobs_handler=marge.lambdas.jobs.nightly_handler
contracts_handler=marge.lambdas.handlers.contracts_handler
mcp_handler=marge.lambdas.handlers.mcp_handler
EOF
echo "== Manifeste =="
cat "$OUT/MANIFEST.txt"
