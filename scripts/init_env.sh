#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_FILE="${ROOT_DIR}/.env.example"
OUTPUT_FILE="${ROOT_DIR}/.env"

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "Template file not found: ${TEMPLATE_FILE}" >&2
  exit 1
fi

if [[ -f "${OUTPUT_FILE}" ]]; then
  read -r -p "${OUTPUT_FILE} already exists. Overwrite? [y/N]: " overwrite
  if [[ "${overwrite}" != "y" && "${overwrite}" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

if ! command -v envsubst >/dev/null 2>&1; then
  echo "envsubst is required." >&2
  echo "Install gettext package (e.g. apt/dnf/brew install gettext)." >&2
  exit 1
fi

read -r -p "USER_USERNAME [user]: " USERNAME_INPUT
USERNAME="${USERNAME_INPUT:-user}"

while true; do
  read -r -s -p "USER_PASSWORD: " PASSWORD1
  echo
  read -r -s -p "Confirm USER_PASSWORD: " PASSWORD2
  echo
  if [[ -z "${PASSWORD1}" ]]; then
    echo "Password must not be empty."
    continue
  fi
  if [[ "${PASSWORD1}" != "${PASSWORD2}" ]]; then
    echo "Passwords do not match. Try again."
    continue
  fi
  break
done

SECRET_KEY="$(openssl rand -hex 32)"
ACCESS_TOKEN_EXPIRE_MINUTES="60"
COOKIE_SECURE="true"
LOGIN_RATE_LIMIT_WINDOW_SECONDS="300"
LOGIN_RATE_LIMIT_MAX_ATTEMPTS="5"
LOGIN_RATE_LIMIT_BLOCK_SECONDS="300"
SEARCH_INDEX_SYNC_MIN_INTERVAL_SECONDS="30"
PREWARM_THUMBNAILS_ON_STARTUP="true"

python3 - <<'PY'
from importlib.util import find_spec
import sys
if find_spec("bcrypt") is None:
    print("bcrypt backend is required. Install with: python3 -m pip install bcrypt", file=sys.stderr)
    raise SystemExit(1)
PY

HASH="$(
  printf '%s' "${PASSWORD1}" | python3 -c $'import sys\nimport bcrypt\np = sys.stdin.read().rstrip("\\r\\n").encode("utf-8")\nif not p:\n    raise SystemExit("empty password")\nif len(p) > 72:\n    raise SystemExit("password must be 72 bytes or less for bcrypt")\nprint(bcrypt.hashpw(p, bcrypt.gensalt()).decode())'
)"
if [[ -z "${HASH}" ]]; then
  echo "Failed to generate USER_PASSWORD_HASH." >&2
  exit 1
fi

# Escape '$' for docker compose interpolation.
HASH_ESCAPED="${HASH//\$/\$\$}"

export SECRET_KEY
export ACCESS_TOKEN_EXPIRE_MINUTES
export USER_USERNAME="${USERNAME}"
export USER_PASSWORD_HASH="${HASH_ESCAPED}"
export COOKIE_SECURE
export LOGIN_RATE_LIMIT_WINDOW_SECONDS
export LOGIN_RATE_LIMIT_MAX_ATTEMPTS
export LOGIN_RATE_LIMIT_BLOCK_SECONDS
export SEARCH_INDEX_SYNC_MIN_INTERVAL_SECONDS
export PREWARM_THUMBNAILS_ON_STARTUP

envsubst <"${TEMPLATE_FILE}" >"${OUTPUT_FILE}"

chmod 600 "${OUTPUT_FILE}"
echo "Generated ${OUTPUT_FILE}"
