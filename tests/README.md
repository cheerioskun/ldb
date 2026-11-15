# Tests

`tooling/` exercises setup, patch export, hooks, and reconstruction using tiny
local Git repositories. Run `make test-tooling`. These tests need no actual LLVM
build and do not claim to validate LDB's generated code or runtime.

Next, on branch `llvm-14`, implement three small C fixtures:

1. **Frame protocol:** nested noinline calls check the saved caller frame,
   canary/generation slots and TLS-published frame pointer. Repeated calls must
   have distinguishable invocation generations.
2. **Program behavior:** eight integer arguments, recursion, an aligned stack
   local and an ordinary host-compiler object preserve exact computed results.
3. **Observable output:** one pthread worker processes tagged request 42 and a
   deliberately slow noinline call. Decode and check its tag, thread identity,
   and expected symbolized call site. Synchronize ordering rather than assuming
   exact scheduling or latency.

Use compiler/runtime path arguments so the same source and assertions run on
both toolchains. Initially use the existing optimized mode, frame pointers,
DWARF 3, no LTO, and disabled sibling-call optimization for stable physical call
shapes. Do not compare exact assembly/IR text, durations, or complete short-call
event counts. Run runtime fixtures serially because the inherited runtime uses
a fixed shared-memory key.

Keep these shared fixtures separate from baseline bug fixes in Git commits.
Cherry-pick the test commits into `main`, establish the same LLVM 14 baseline
there, then upgrade `main` to LLVM 23. Diagnose inherited failures on `llvm-14`
before treating them as port failures.
