#!/bin/sh
set -eu
PV_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -m venv "$PV_DIR/.venv"
"$PV_DIR/.venv/bin/python" -m pip install -r "$PV_DIR/requirements.txt"
printf '%s\n' 'PhantomView instalado. Inicia: sh run.sh serve --open'
