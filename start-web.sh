#!/bin/sh
set -eu
SCRIPT_DIR=$(dirname "$0")
ROOT=$(CDPATH= cd "$SCRIPT_DIR" 2>/dev/null && pwd -P)
cd "$ROOT"
exec uv run macmaid ui "$@"
