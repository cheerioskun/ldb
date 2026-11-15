#define _GNU_SOURCE
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include "ldb/tag.h"

static atomic_int stop_requests;
static atomic_int release_worker;

__attribute__((noinline)) void slow_leaf(void) {
  struct timespec delay = {.tv_nsec = 20000000};
  nanosleep(&delay, NULL);
}

__attribute__((noinline)) void request_handler(void) {
  slow_leaf(); /* A STACK event stores this return site, inside request_handler. */
  __asm__ volatile("" : : : "memory");
}

static void *worker(void *arg) {
  (void)arg;
  printf("WORKER_TID=%ld\n", syscall(SYS_gettid));
  ldb_tag_set(42);
  while (!atomic_load(&stop_requests)) request_handler();
  ldb_tag_unset(42);
  /* Keep this thread's event buffer alive until the test has read TAG_UNSET.
   * The inherited runtime does not guarantee a final drain on thread exit. */
  while (!atomic_load(&release_worker)) {
    struct timespec delay = {.tv_nsec = 1000000};
    nanosleep(&delay, NULL);
  }
  return NULL;
}

int main(void) {
  setvbuf(stdout, NULL, _IOLBF, 0);
  pthread_t thread;
  assert(pthread_create(&thread, NULL, worker, NULL) == 0);
  assert(getchar() == 'q'); /* Runner has observed the tagged stack event. */
  atomic_store(&stop_requests, 1);
  assert(getchar() == 'x'); /* Runner has also observed TAG_UNSET. */
  atomic_store(&release_worker, 1);
  assert(pthread_join(thread, NULL) == 0);
  puts("EVENTS OK");
  return 0;
}
