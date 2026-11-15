# LDB

Tail-latency debugger: a small LLVM backend patch, an application runtime, and
offline analysis tools. LLVM is an upstream submodule; our compiler changes
are ordinary patch files versioned alongside the runtime and tests.

`main` initially reproduces the existing LLVM 14 implementation, including the
`ARCH_GET_FS` support for older x86-64 CPUs. The LLVM 23 upgrade has not started.

## Layout

```text
third_party/llvm/     upstream LLVM submodule, pinned to an unmodified commit
patches/llvm/         compiler patches and their application order (series)
runtime/             libldb.a and the libshim.so preload library
analysis/            original event decoding and timeline scripts
apps/, web/          original example/application recipes and dashboard
scripts/             prepare, build, export, and verify commands
.githooks/           automatic patch export and commit validation
tests/tooling/       tests for repository preparation and hook behavior
docs/                development workflow and baseline provenance
```

## Prepare and build

Development/build target: Linux x86-64. Setup and Git-tooling tests also work
on macOS; the LDB runtime itself uses Linux facilities.

```sh
git clone https://github.com/cheerioskun/ldb.git
cd ldb
make setup
make                     # builds the required LLVM tools, then the runtime
```

Need Git, Python 3.10+, CMake 3.20+, Ninja, and a host C/C++ compiler. A full
compiler build is substantial. `LDB_BUILD_JOBS=2` is the conservative default;
raise it explicitly if the machine has sufficient memory. Only the X86 target
is built, with one link job at a time.

Setup initializes the upstream submodule, selects the LLVM/Clang/CMake source
directories, applies our patches, and installs the project hooks. Re-running
it preserves local development edits. Build outputs stay under `build/llvm`.

Run the small example after building:

```sh
make -C apps/helloworld
cd apps/helloworld
LD_PRELOAD=../../runtime/libshim.so ./hello
```

Most application recipes in `apps/` are inherited research workloads requiring
their own dependencies/path settings. `apps/demo` additionally requires libc++.
See [provenance](docs/provenance.md) for the exact imported source.

## Edit LLVM and commit LDB

```sh
cd third_party/llvm
git switch -c ldb-work       # once, if starting from setup's detached checkout
# Edit compiler code, build, and test.
git add llvm/path/to/file
git commit -m "Describe compiler change"
cd ../..

# The submodule post-commit hook already exported/staged compiler patches.
# Stage whichever parent-project changes belong in this commit.
git add runtime tests
git commit -m "Describe the LDB change"
git push origin main
```

The parent pre-commit hook checks/re-exports the compiler patches. Do not stage
`third_party/llvm` after making local compiler commits: its recorded pin must
remain at upstream. If accidentally staged, use
`git restore --staged third_party/llvm`; local LLVM edits/commits remain intact.
Parent runtime/test files retain their normal partial-staging behavior.
Git may show the prepared submodule as having local commits; that is expected.
The recorded parent pin still identifies upstream, while patches carry our work.

Compiler commits are local working history. Only the exported patch files are
pushed to our repository; an LLVM fork and separate patch branch are unnecessary.
See [the detailed workflow](docs/development.md), including branch changes and
toolchain updates.

## Verify

```sh
make test-tooling          # small real-Git fixtures; no LLVM download/build
make check-patches         # replay staged patches in an isolated temporary index
```

CI runs these checks and reconstructs the compiler source from the public
upstream pin. The three intended LDB behavior tests are **not implemented yet**;
passing tooling checks does not establish compiler/runtime correctness.

## Branch sequence

1. Bootstrap `main` with the existing LLVM 14 implementation (this state).
2. Create `llvm-14` and establish the minimal LDB behavior suite there.
3. Keep shared tests/tooling in commits separate from LLVM 14/runtime fixes.
4. Cherry-pick the shared test commits into `main` and run them on its LLVM 14
   baseline before changing the toolchain.
5. Upgrade only `main` to LLVM 23; run the same behavioral contracts there.

This keeps `llvm-14` as a working reference and distinguishes inherited bugs
from port regressions. [Initial behavior-test plan](tests/README.md).
