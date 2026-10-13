#!/bin/sh
# Build inside a staged context. No downloads or package installation here.
set -eu
cd -- "$(dirname -- "$0")"
mkdir -p bin
compiler=${CXX:-g++}
for lane in sedge flora candidate; do
  "$compiler" -O3 -std=c++20 -DNDEBUG -Isources/sedge/vendor "sources/$lane/main.cpp" -o "bin/$lane"
done
"$compiler" -O3 -std=c++20 -DNDEBUG -DLANG_EN \
  -Isources/networktools/networktools sources/checker/src/main.cpp -o bin/checker
chmod +x run.sh bin/sedge bin/flora bin/candidate bin/checker
