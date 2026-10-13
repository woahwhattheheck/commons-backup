#!/bin/sh
set -eu
if [ "$#" -ne 4 ]; then
  echo "Usage: $0 network.json traffic.json scenario.json output.json" >&2
  exit 2
fi
solver_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$solver_dir/supervisor.py" "$1" "$2" "$3" "$4"
