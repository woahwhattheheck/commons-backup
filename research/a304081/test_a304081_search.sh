#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bin="$(mktemp)"
trap 'rm -f "$bin"' EXIT

g++ -O3 -std=c++20 -Wall -Wextra -pedantic a304081_search.cpp -o "$bin"

"$bin" self-test | grep -F 'SELF_TEST_PASS cases=13'

out="$("$bin" count 6447154629)"
grep -F 'COUNT n=6447154629 a=2' <<<"$out"
grep -F 'REP p=6447121859 k=15 m=0 offset=32770' <<<"$out"
grep -F 'REP p=5958840611 k=15 m=12 offset=488314018' <<<"$out"

"$bin" scan 8 100 | grep -F 'SCAN_DONE lo=8 hi=100'
"$bin" verify-range 8 100 | grep -F 'RANGE_DONE lo=8 hi=100 count=93'

echo 'A304081_TEST_PASS'
