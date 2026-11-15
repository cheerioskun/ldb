/* Tiny stock-compiled runtime for the two compiler contract tests.
 * The third test uses the real LDB runtime, monitor, logger and preload shim. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern __thread uint64_t __ldb_reserved[50];
int test_init_calls;

void __ldbInit(void) {
  uintptr_t fs = (uintptr_t)__builtin_thread_pointer();
  uintptr_t first = (uintptr_t)__ldb_reserved;
  uintptr_t end = first + sizeof(__ldb_reserved);
  if (++test_init_calls != 1 || fs - 344 < first || fs - 208 > end) {
    fputs("LDB initialization/TLS reservation contract failed\n", stderr);
    exit(1);
  }
  uint64_t canary = UINT64_C(0xdeadbeef00000000);
  __asm__ volatile("movq %0, %%fs:-216" : : "r"(canary) : "memory");
}

void __ldbExit(void) {
  if (test_init_calls != 1) abort();
  puts("HOOKS init=1 exit=1");
}
