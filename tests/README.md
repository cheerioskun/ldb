# Tests

`make test-tooling` exercises setup, patch export, hooks and reconstruction in
tiny local Git repositories. It needs no LLVM build and does not validate LDB.

After building the compiler and runtime, run `make test-behavior` on Linux x86-64.
There are three contracts, each with a small C fixture:

| Test | What it checks |
| --- | --- |
| [Frame](behavior/frame.c) | Saved caller RBP; canary and invocation generation; TLS-published RBP on entry and after a child returns; return address resolves to the calling function. |
| [ABI](behavior/abi.c) | Eight integer arguments; recursion; a 64-byte-aligned stack local; calls to and callbacks from an ordinary host-compiled object. Exact arithmetic results must survive. |
| [Events](behavior/events.c) | The real runtime emits tag 42 and a stack event for the same worker TID, with a return site symbolized inside `request_handler`; the tag is then unset. |

The first two use [tiny host-compiled hooks](behavior/hooks.c). They check that
the compiler injects initialization/exit calls and reserves the TLS locations,
without depending on the monitor/logger. The third uses `libldb.a`, preloaded
`libshim.so`, actual pthreads, the monitor, the logger and the binary trace.

The runtime samples physical frames. A STACK event's address is the callee's
**return site in its caller**, not the callee's entry address. Thus the slow
`slow_leaf` call is expected to resolve inside `request_handler`. The test
requires an observed event, not an exact duration or count of every short call.

The runner waits for a tagged stack event before asking the worker to stop. It
then waits for TAG_UNSET to reach the log before letting the worker exit. This
keeps its buffer alive: the inherited runtime does not promise a final drain at
thread exit. Shutdown loss and arbitrary thread lifetimes need separate tests
and runtime work; this minimal suite does not claim to cover them.

Use alternate toolchains without changing sources or assertions:

```sh
python3 tests/behavior/run.py \
  --clang /path/to/compiler/bin/clang \
  --symbolizer /path/to/compiler/bin/llvm-symbolizer \
  --runtime /path/to/matching/runtime \
  --host-cc /usr/bin/cc \
  --output /path/to/artifacts
```

Each run retains executables, logs, tool versions, `ldb.data`, `maps.data` and a
short decoded observation in a fresh directory under `build/behavior/`.

Scope: optimized C, frame pointers, DWARF 3, no LTO, no PIE, disabled sibling-call
optimization. Neither version strings nor exact IR/assembly listings are test
oracles. This is a starting baseline, not evidence for C++ exceptions, unwinding,
varargs, arbitrary TLS layouts, other architectures, or production safety.

Runtime tests must run serially. The runner claims fixed shared-memory key
401916 exclusively and removes only its own segment afterward. It refuses to
reuse an existing segment. Failures retain their artifacts for inspection.

Keep shared test changes separate from baseline fixes. Work stops at the LLVM
14 milestone for collaborative review before any cherry-pick or LLVM 23 port.
