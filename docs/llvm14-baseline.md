# LLVM 14 baseline: review milestone

On 2026-11-15, the patched LLVM 14 compiler and LDB runtime built on Linux x86-64,
and all three behavior contracts passed there. A repeat of the same suite passed
in 10 consecutive fresh processes. A final run after syncing the committed
runtime fixes also passed. These are executable checks, not estimates of effort.

`main` remains at `b1b0528250cbbe3f3d7b42d7882174ae75fb2b80`. All new work is on
`llvm-14`. There has been no cherry-pick into `main` and no LLVM 23 implementation
change.

## Review the contracts first

Read [the three-test guide](../tests/README.md), then the fixtures:

1. [Frame protocol](../tests/behavior/frame.c): saved caller frame, canary,
   generation, published TLS frame pointer and symbolized return sites.
2. [Ordinary program behavior](../tests/behavior/abi.c): eight arguments,
   recursion, aligned locals and a host-compiled caller/callback.
3. [Real runtime output](../tests/behavior/events.c): a tagged pthread worker,
   a sampled return site and clean process exit.

The first two have tiny host-compiled lifecycle hooks. The third uses the actual
runtime, preload shim, monitor and logger. The runner accepts explicit compiler,
symbolizer and runtime paths; it does not branch on LLVM version.

The shared tests were introduced in `d8270db`; `406887f` improves failure logging.
They are separate from the baseline fixes below. The suite is 155 lines of C
across five small files, plus the Python runner.

## What the tests and build exposed

| Observation | Fix | Commit |
| --- | --- | --- |
| The sparse checkout omitted LLVM's required `third-party` build sources. | Include them; setup can expand sparse paths while preserving source edits. | `c92309b` |
| LLVM 14's `Signals.h` uses `uintptr_t` without including its defining header with current host C++ libraries. | Add `<cstdint>` in a separate compiler patch. | `d3cff0c` |
| Both CI runs reached the expected runtime events, then failed at worker exit. GDB on Emulab stopped in glibc `start_thread`, with RBP equal to zero. | Preserve the native caller's saved RBP; stop scanning at the recorded LDB root instead of zeroing its saved link. Use the actual RBP for thread-root setup. | `4ecd498` |
| Emulab placed worker stacks around `0x7d…`; the monitor rejected everything below `0x7f0000000000`, producing no stack events. | Obtain the stack's lower bound with pthread APIs and validate against it and the recorded root. Rebuild every runtime object when the shared layout or compiler changes. | `5053b11` |

GDB reproduced the original worker-exit SIGSEGV and showed the same fixture
exiting normally after the saved-RBP fix. The normal suite then passed with
ASLR enabled after the stack-bounds fix. Its assertions were not weakened.

One observed result was tag 42, worker TID 34433, a positive sampled latency,
and return site `request_handler` at `events.c:23`. Addresses, TIDs and durations
are observations, not test constants or performance guarantees.

## Reproduce

The native build machine has an Intel Xeon E5530, 8 logical CPUs, about 12 GiB
RAM, Ubuntu 24.04 and Clang 18 as host compiler. This CPU has no FSGSBASE support;
the inherited `ARCH_GET_FS` runtime path works in the executed end-to-end test.

These settings reproduce the native compiler build. The explicit GCC directory
avoids this machine's incomplete newer GCC development installation:

```sh
git switch llvm-14
CC=clang CXX=clang++ LDB_BUILD_JOBS=6 ./scripts/build-llvm.sh \
  -DCMAKE_CXX_FLAGS=--gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/13 \
  -DLLVM_USE_LINKER=lld \
  -DCMAKE_CXX_FLAGS_RELEASE="-O1 -DNDEBUG" \
  -DCMAKE_C_FLAGS_RELEASE="-O1 -DNDEBUG"
make -C runtime
make test-behavior
make test-tooling
make check-patches
```

The LLVM tools themselves use host optimization `-O1`, with LLVM assertions
enabled. Test fixtures use `-O3`, frame pointers, DWARF 3, no PIE or LTO, and
disabled sibling-call optimization. The host compiler needs its C++ development
library; Ninja and lld must be installed for the command above.

The compiler's unmodified upstream pin remains
`5f66e721ec1d099cf2370235ce122cf47c287308`. Applying the three patches reconstructs
tree `bd44f89e81045d94842df09a0725b134240c37e2`. Temporary submodule commit IDs
can differ between checkouts; the source tree is what is verified.

The native build produced clang, opt, llc, FileCheck and llvm-symbolizer.
The Git workflow suite has 11 passing tests. CI source reconstruction also
passed. The CI rebuild for the two runtime fixes is pending; the two earlier
CI failures are retained evidence of the original runtime exit bug.

## Limits for our review

The runtime test waits until its required records reach the log before allowing
the worker to exit. It does not establish lossless delivery at arbitrary thread
exit or shutdown. Sampling is not exact entry/exit instrumentation, and the
recorded address is the callee's return site inside its caller.

Inspection also found that registry readers do not take the writer's lock while
threads register or retire. That possible lifetime race is a separate review
item; it was not the cause shown by the captured SIGSEGV. A reader-lock candidate
was set aside and is not included in these commits. Ten successful runs do not
establish that the runtime is free of concurrency bugs.

The suite does not cover C++ unwinding, arbitrary TLS layouts, varargs, deep
stacks, thread-slot reuse, other architectures or production performance.
Those remain outside this initial milestone.
