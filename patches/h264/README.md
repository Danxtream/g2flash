# G2 H.264 Decoder Wrapper

C ABI wrapper around Sub0h264 for use by g2flash firmware patches.

## Decoder pipeline

BLE / test data
-> complete raw or Annex-B NAL
-> g2_h264_decode_nal()
-> Sub0h264 parseNalUnit()
-> H264Decoder::processNal()
-> decoded 8-bit Y plane
-> centered packed-A4 G2 framebuffer

Sub0h264 remains C++ internally.

The g2flash firmware should interact with the decoder through
g2_h264.h only.

## Mode-11 bring-up protocol

- `[11][0]` stops and releases the decoder.
- `[11][1][streamIdLE32]` starts a fresh decoder session and displays its allocation status.
- `[11][2]` resets the active decoder and its stream status.
- `[11][3][NAL]` decodes one complete NAL.
- `[11][4]` displays 0/5/10/15 intensity bands without allocating the decoder.
- `[11][5]` displays the current decoder, NAL, frame, and timing status.
- `[11][6][streamIdLE32][sequenceLE32][NAL]` reliably decodes one complete NAL.
- `[11][7]` displays the asymmetric lens/orientation probe.
- `[11][8]` emits master-side protocol-v9 telemetry without repainting.
- `[11][9][0]` selects centered native-size presentation (the START default).
- `[11][9][1]` selects nearest-neighbor 2x presentation when the coded frame fits;
  for example, 320x192 is displayed as 640x384 with black bars above and below.

Sequenced NALs are decoded strictly in order. Up to three future NALs are retained
while the missing sequence is retried. V9 uses four fixed 4 KiB snapshot slots: one
may be owned by the active decode and three by the ordered queue. Repeated sequences
are acknowledged through telemetry without being decoded twice.

Protocol-v9 telemetry retains the earlier fields while suppressing intermediate
dispatcher/ingress notifications. Normal playback emits an authoritative completion
only after the physical framebuffer presents a frame, leaving BLE bandwidth available
for video. It also reports queue capacity, queued bytes,
and failure-only decoder-arena usage. It distinguishes arena rebind failure, arena
exhaustion, firmware-heap allocation failure, reorder wait, queue-full rejection,
and snapshot-allocation failure. Successful SPS and PPS input updates the status
screen. The first decoded frame
is centered on the physical framebuffer without a diagnostic overlay. Decoder,
queue, retry, and presentation state is reported to the phone through telemetry.

## Current limitations

- V9 reserves the stock image-container buffers while H.264 mode is active and
  rebinds the decoder arenas before every NAL while preserving their used offsets. The
  large decoder frames/context arrays and snapshot queue do not use firmware heap,
  but small STL bookkeeping allocations still do.
- The bounded hardware path currently targets 320x192 I420 with two DPB frames and
  mode-11 messages no larger than one 4 KiB snapshot slot.
- Decode and presentation performance is not yet verified on G2 hardware.
- The firmware entry point requires a complete reassembled NAL per mode-11
  decode command; it does not accept arbitrary BLE fragments.
- Cropped/visible SPS dimensions are not exposed yet.
