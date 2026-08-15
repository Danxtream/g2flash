G2 H.264 bridge diagnostic v2

Why this exists:
The v1 bridge counters were packed into H264 telemetry, but the snapshot producer
emits its telemetry before the stock completion bridge executes. On a failing
frame with no later deferred callback, the visible bridge counters are therefore
one frame behind and cannot localize the failure.

V2 keeps the same bridge hooks and counter packing, but emits H264 telemetry at
each instrumented bridge stage:
  gate -> emit -> schedule(return) -> delayed send -> E0 op3

Only patches/zlib_glue.c changes. patch_compress.py from v1 remains valid.
The ZIP is intentionally rooted at patches/ (no extra nested directory).
