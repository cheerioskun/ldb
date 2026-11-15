/* Compile this with the ordinary host compiler: both directions cross the ABI. */
typedef long (*callback_t)(long, long, long, long, long, long, long, long);

long host_sum(long a, long b, long c, long d, long e, long f, long g, long h) {
  return a + 2*b + 3*c + 4*d + 5*e + 6*f + 7*g + 8*h;
}

long host_call(callback_t callback) {
  return callback(11, 12, 13, 14, 15, 16, 17, 18);
}
