G2 H264 dispatcher diagnostic V3
================================

Baseline
--------
- zlib_glue.c is based on the flashed V2 source (SHA256
  787c06665f819664068aa48e70cb2a3a9d91f6318dd8b7e6a39e52dd9a919163).
- patch_compress.py is based on the bridge-diagnostic V1/V2 patch script.
- V2 outer bridge probes remain installed; V3 repurposes telemetry diag[2]/diag[3]
  for the inner FUN_00496544 dispatcher breadcrumb because V2 proved the outer
  bridge reaches E0 op=3 on the failing 320x192 seq3.

V3 telemetry
------------
Existing H264STAT format is unchanged. Interpret:
  diag=<snapshot_count>/<deferred_count>/<stage>/<detail>

stage:
  0  H264 snapshot committed; detail = H264 sequence number
  1  E0 op=3 entered; detail = op3 payload length
  2  stock dispatcher passed event type 11 AND descriptor halfword +2 == 16;
     detail = 16
  3  stock 0x493fa8 lookup returned; detail encoding:
       bit 0       = lookup result non-null
       bits 8..15  = returned node subtype, or 0xff if null
       bits 16..31 = lookup key low 16 bits
  4  returned lookup node passed subtype == 2; detail = 2
  5  event field +24 failed the 0x4c comparison; detail = 0x4c
  6  malloc entered (therefore field +24 == 0x4c and mode is 1 or 2);
     detail = requested size
  7  malloc returned; bit31=1 means non-null, low31=requested size
  8  prep entered; high nibble 1 = stock 0x4e0c34 path, 2 = stock 0x4e0c0c path;
     low 28 bits = size argument
  9  prep returned; high nibble identifies path, bit0=return nonzero
 10  image_deferred entered; detail = len

Stock BL sites added by V3
--------------------------
  0x496720  post type==11 && descriptor +2==16; wraps stock 0x43d0ce
  0x496768  wraps stock 0x493fa8 lookup
  0x496824  post subtype==2; wraps stock 0x43d0ce
  0x496886  wraps stock malloc 0x474cd2
  0x4968ea  wraps stock prep 0x4e0c0c
  0x4968fa  wraps stock prep 0x4e0c34
  0x496ab2  field+24 != 0x4c branch; wraps stock 0x43d0ce

All seven original 4-byte BL encodings were checked directly against the stock
2.2.6.10 binary before packaging. V3 does not replace CMP/BNE instructions.
Each wrapper calls the exact original stock callee and returns its result unchanged.

Local validation performed
--------------------------
- zlib_glue.c compiled successfully with clang 17 for thumbv7em-none-eabi using
  the project's freestanding C flags.
- patch_compress.py passes Python bytecode compilation.
- all seven V3 stock BL old-byte guards match the stock 2.2.6.10 firmware.
- all V3 exported probe symbols are present in the ARM object.

The full combined C++ firmware build was not run in the Linux validation environment
because this project build.py contains Windows Arm GNU C++ include paths. Build the
bundle in the normal Windows g2flash project with build_cfw.sh --update-patches.
