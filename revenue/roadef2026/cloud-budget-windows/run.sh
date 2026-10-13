#!/bin/sh
set -eu
if [ "$#" -ne 5 ]; then
  echo "usage: $0 network.json traffic.json scenario.json incumbent.json output.json" >&2
  exit 2
fi
CLOUD_INITIAL_SOLUTION=$4
export CLOUD_INITIAL_SOLUTION
exec "$(dirname "$0")/solver" "$1" "$2" "$3" "$5"
