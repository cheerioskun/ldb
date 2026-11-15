#include <assert.h>
#include <stdint.h>
#include <stdio.h>

typedef long (*callback_t)(long, long, long, long, long, long, long, long);
extern long host_sum(long, long, long, long, long, long, long, long);
extern long host_call(callback_t);

__attribute__((noinline)) long eight_args(
    long a, long b, long c, long d, long e, long f, long g, long h) {
  /* Volatile storage keeps the stack arguments and aligned frame observable. */
  _Alignas(64) volatile long values[8] = {a, b, c, d, e, f, g, h};
  assert((uintptr_t)values % 64 == 0);
  long sum = 0;
  for (int i = 0; i < 8; ++i) sum += (i + 1) * values[i];
  return sum;
}

__attribute__((noinline)) long recurse(long depth) {
  volatile long saved = depth;
  if (depth == 0) return 1;
  return saved + recurse(depth - 1);
}

int main(void) {
  assert(eight_args(1, 2, 3, 4, 5, 6, 7, 8) == 204);
  assert(host_sum(1, 2, 3, 4, 5, 6, 7, 8) == 204);
  assert(host_call(eight_args) == 564);
  assert(recurse(10) == 56);
  puts("ABI OK");
  return 0;
}
