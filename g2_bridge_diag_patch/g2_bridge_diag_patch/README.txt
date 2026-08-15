H.264 snapshot->deferred bridge diagnostic patch

Based on the exact g2flash_re.zip uploaded in this conversation.
Modified files:
  patches/zlib_glue.c
  patches/patch_compress.py

Purpose:
  Instrument the stock RIGHT-side image-completion bridge at five boundaries:
    gate -> emit -> delayed schedule -> delayed send -> E0 op3 -> existing image_deferred

Telemetry packing for the existing diag[4] display:
  diag0 = snapshot_count
  diag1 = deferred_count
  diag2 low bytes (little-endian):
      bits  0.. 7 = gate_calls
      bits  8..15 = emit_calls
      bits 16..23 = schedule_calls
      bits 24..31 = delayed_send_calls
  diag3 low bytes (little-endian):
      bits  0.. 7 = e0_op3_calls
      bits  8..15 = schedule_ok
      bits 16..23 = legacy h264_diag_flags low byte
      bits 24..31 = last_deferred_snapshot_count low byte

For the short startup test counters are reset by H264 START, so each byte can be read directly without wrap concerns.

Patched stock BL sites (old bytes asserted):
  0x4db974  67 f7 ac fd  single complete -> 0x4434d0 gate
  0x4dbd66  67 f7 b3 fb  multi complete  -> 0x4434d0 gate
  0x4db986  fe f7 fc fc  single complete -> 0x4da382 emit
  0x4dbd76  fe f7 04 fb  multi complete  -> 0x4da382 emit
  0x4da498  80 f7 17 fb  field 0x4c -> 0x45aaca delayed scheduler
  0x45aabc  0a f0 79 f8  delayed callback -> 0x464bb2 send
  0x4e16ec  b4 f7 2a ff  E0 op3 -> 0x496544 dispatcher

Build on Dan's Windows g2flash environment using the normal project sequence:
  bash ./build_cfw.sh --update-patches
  update OUT_SHA256 in build_cfw.sh to the new reported hash
  bash ./build_cfw.sh --update-patches
  then propagate cfw_patches.json into Faceclaw, rebuild APK, install, and flash via Faceclaw.

Validation performed here:
  - exact old bytes verified against uploaded s200_firmware_ota_extracted.bin
  - patch_compress.py parses with Python
  - modified zlib_glue.c compiles standalone for thumbv7em with clang
Full combined firmware build could not be completed in this Linux sandbox because uploaded build.py contains Dan's Windows Arm-GNU C++ include paths.
