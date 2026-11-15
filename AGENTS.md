# Working on LDB

- Keep the LLVM submodule pinned to unmodified upstream source. Compiler changes
  belong in `patches/llvm/`, on the same branch as runtime/tests.
- Use `main` for initial setup. The planned reference branch is `llvm-14`.
  Do not create `codex/` branches.
- Run `make setup` in a new clone to prepare LLVM and activate both hooks.
  Commit compiler edits locally inside the submodule; hooks export the series.
  Do not stage the modified submodule HEAD as a new upstream pin.
- Keep shared behavioral-test changes separate from toolchain-specific fixes
  so the tests can be cherry-picked from `llvm-14` into `main`.
- For Git workflow changes, run `make test-tooling` and `make check-patches`.
  Preserve user source edits and partial staging; never reset/clean them away.
- Tooling checks are not evidence that the compiler/runtime works. Report
  separately which toolchain builds and behavioral tests actually ran.
- Make observations and uncertainty inspectable. Challenge consequential weak
  assumptions without withholding concrete, authorized execution.
