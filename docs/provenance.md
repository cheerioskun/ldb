# Baseline provenance

LDB source: [cheerioskun/llvm14-ldb](https://github.com/cheerioskun/llvm14-ldb),
commit `5ead9a59c0ce7b67ee5d4d0acbc646f582c0fada`, descended from
[inhocho89/llvm14-ldb](https://github.com/inhocho89/llvm14-ldb).

The upstream LLVM ancestor is
`5f66e721ec1d099cf2370235ce122cf47c287308`. It is the recorded ancestor used by
the original fork, not an assertion that this is the final LLVM 14 release.

Compiler differences are imported as two focused patches: IR/TLS integration
and x86 backend integration. Together they reproduce the source fork's entire
`llvm/` subtree exactly: 17 files, 388 inserted lines, 4 removed lines. The
inactive `X86LatencyDebug.cpp` implementation is intentionally preserved in the
baseline; removing it is a later explicit change.

`runtime/` is the original `libldb/`, including the merged `ARCH_GET_FS` change
for older CPUs. Runtime C/header sources are unchanged by the layout import.
Only its Makefile is adjusted to find the relocated compiler build, replace
archive members correctly, and clean generated files reliably.

`analysis/` is the original `scripts/`. `apps/` and `web/` are retained for
reference. Build recipes/docs are adjusted where necessary for the new runtime,
compiler, and analysis locations. These inherited analysis/dashboard tools have
not been modernized or validated by the tooling tests.

The compiler patches credit the original author and identify the exact source
revision. Their import commits are new; the full original development history
remains in the source fork. The upstream LLVM license is preserved in
`licenses/LLVM.txt` and in the submodule. This reorganization does not claim to
relicense imported LDB code.

The baseline source's FS-base syscall change removes the original FSGSBASE
instruction dependency. Building/running LDB and establishing its behavior
suite are the next phase.
