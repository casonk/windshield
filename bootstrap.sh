#!/usr/bin/env bash
# Create a virtualenv and install windshield into it.
#
# Why this exists: the previous instruction, a bare `pip install -e ".[dev]"`,
# is refused on current Debian, Ubuntu, Arch and openSUSE. Since PEP 668 those
# distros mark the system Python "externally managed", and pip declines rather
# than write into a tree the system package manager owns:
#
#     error: externally-managed-environment
#
# Fedora still permits it, which is why the old instruction appeared to work on
# some machines and not others.
#
# The second reason: every browser backend here is an *optional* extra, so
# `.[dev]` alone installs the test tooling and no way to drive a page. This
# script reports which backends actually resolved, instead of leaving you to
# discover it at the first ImportError.
#
# Usage:
#   ./bootstrap.sh                  # venv + .[dev]
#   ./bootstrap.sh --all            # .[all,dev] — every browser backend
#   ./bootstrap.sh --extras a,b     # pick your own, e.g. playwright,http
#   ./bootstrap.sh --no-dev         # runtime only
#   ./bootstrap.sh --pre-commit     # also install the pre-commit hooks
#   ./bootstrap.sh --venv PATH      # somewhere other than ./.venv

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${REPO_ROOT}/.venv"
PYTHON="${PYTHON:-python3}"
WITH_DEV=1
WITH_PRECOMMIT=0
EXTRA_LIST=""
MIN_PYTHON="3.10"

usage() {
  sed -n '2,27p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) EXTRA_LIST="all"; shift ;;
    --extras) EXTRA_LIST="${2:?--extras needs a comma-separated list}"; shift 2 ;;
    --no-dev) WITH_DEV=0; shift ;;
    --pre-commit) WITH_PRECOMMIT=1; shift ;;
    --venv) VENV="${2:?--venv needs a path}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: '$PYTHON' not found. Install Python ${MIN_PYTHON}+ or set PYTHON=/path/to/python3." >&2
  exit 1
fi

# Fail on the version here rather than letting pip fail later with a wall of
# resolver output that buries the actual cause.
"$PYTHON" - "$MIN_PYTHON" <<'PY' || exit 1
import sys
minimum = tuple(int(p) for p in sys.argv[1].split("."))
if sys.version_info[:len(minimum)] < minimum:
    have = ".".join(str(p) for p in sys.version_info[:3])
    print(f"error: this project needs Python {sys.argv[1]}+, found {have}", file=sys.stderr)
    raise SystemExit(1)
PY

echo "==> creating virtualenv at ${VENV}"
"$PYTHON" -m venv "$VENV"

# Windows layout differs; support Git Bash / WSL invocations too.
VPY="${VENV}/bin/python"
[ -x "$VPY" ] || VPY="${VENV}/Scripts/python.exe"
VBIN="$(dirname "$VPY")"

echo "==> upgrading pip"
"$VPY" -m pip install --upgrade pip --quiet

EXTRAS=()
[ -n "$EXTRA_LIST" ] && IFS=',' read -r -a EXTRAS <<< "$EXTRA_LIST"
[ "$WITH_DEV" -eq 1 ] && EXTRAS+=("dev")

if [ ${#EXTRAS[@]} -gt 0 ]; then
  TARGET=".[$(IFS=,; echo "${EXTRAS[*]}")]"
else
  TARGET="."
fi

echo "==> installing ${TARGET} (editable)"
cd "$REPO_ROOT"
"$VPY" -m pip install -e "$TARGET"

echo "==> verifying the install"
"$VPY" -c "import windshield; print('  import windshield: ok')"

# Every browser backend is optional, so a successful install still tells you
# nothing about whether you can drive a page. Say which ones are actually here.
"$VPY" - <<'PY'
import importlib

backends = {
    "playwright": "page interaction (the primary backend)",
    "selenium": "selenium driver support",
    "undetected_chromedriver": "undetected-chromedriver support",
    "requests": "windshield.http",
    "bs4": "HTML parsing for windshield.http",
}

missing = []
for module, purpose in backends.items():
    try:
        importlib.import_module(module)
    except ImportError:
        missing.append((module, purpose))
        print(f"  [ ] {module:26} {purpose}")
    else:
        print(f"  [x] {module:26} {purpose}")

if any(m == "playwright" for m, _ in missing):
    print(
        "\nnote: playwright is not installed. windshield.page cannot drive a\n"
        "      browser without it. Install it with:\n"
        "          ./bootstrap.sh --extras playwright\n"
        "      or ./bootstrap.sh --all"
    )
PY

if [ "$WITH_PRECOMMIT" -eq 1 ]; then
  echo "==> installing pre-commit hooks"
  "$VPY" -m pip install --quiet pre-commit
  "${VBIN}/pre-commit" install
fi

cat <<EOF

Done. Activate the environment with:

    . ${VENV}/bin/activate

Run the tests:

    ${VPY} -m pytest -q
EOF

if "$VPY" -c "import playwright" >/dev/null 2>&1; then
  cat <<EOF

Playwright's Python package is installed, but its browser binaries are a
separate download:

    ${VBIN}/playwright install chromium
EOF
fi
