#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$project_root/scripts/setup-llvm.sh"
cmake -S "$project_root/third_party/llvm/llvm" -B "$project_root/build/llvm" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLVM_ENABLE_PROJECTS=clang \
    -DLLVM_TARGETS_TO_BUILD=X86 \
    -DLLVM_ENABLE_ASSERTIONS=ON \
    -DLLVM_INCLUDE_TESTS=ON \
    -DLLVM_BUILD_TESTS=OFF \
    -DLLVM_INCLUDE_EXAMPLES=OFF \
    -DLLVM_ENABLE_BINDINGS=OFF \
    -DLLVM_PARALLEL_LINK_JOBS=1
cmake --build "$project_root/build/llvm" \
    --parallel "${LDB_BUILD_JOBS:-2}" \
    --target clang opt llc FileCheck llvm-symbolizer
