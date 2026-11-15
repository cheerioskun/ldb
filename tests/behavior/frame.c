#include <assert.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

extern int test_init_calls;

__attribute__((noinline)) uint64_t frame_probe(uintptr_t parent) {
  uintptr_t rbp, published;
  __asm__ volatile("movq %%rbp, %0; movq %%fs:-280, %1"
                   : "=r"(rbp), "=r"(published) : : "memory");
  const uint64_t *frame = (const uint64_t *)rbp;
  assert(published == rbp);
  assert(frame[0] == parent);
  assert(frame[1] >> 32 == UINT64_C(0xdeadbeef));
  uint64_t generation = frame[2];
  printf("FRAME_SITE=0x%" PRIx64 "\n", frame[3]);
  return generation;
}

__attribute__((noinline)) void frame_parent(void) {
  uintptr_t rbp;
  __asm__ volatile("movq %%rbp, %0" : "=r"(rbp));
  uint64_t first = frame_probe(rbp);
  uint64_t second = frame_probe(rbp);
  assert(second > first);
  uintptr_t published;
  __asm__ volatile("movq %%fs:-280, %0" : "=r"(published) : : "memory");
  assert(published == rbp); /* A child's epilogue restores the caller. */
}

int main(void) {
  assert(test_init_calls == 1);
  frame_parent();
  puts("FRAME OK");
  return 0;
}
