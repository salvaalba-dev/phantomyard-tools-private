#!/bin/sh
set -eu
PV_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$PV_DIR/.venv/bin/python" "$PV_DIR/phantomview.py" "$@"
