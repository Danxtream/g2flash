#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    G2_H264_ERROR          = -1,
    G2_H264_NEED_MORE_DATA = 0,
    G2_H264_FRAME_READY    = 1
} g2_h264_result_t;

typedef struct
{
    void* first;
    size_t first_size;
    void* second;
    size_t second_size;
} g2_h264_memory_t;

/* Mutable arena bookkeeping lives in the firmware CFW context. Injected code
 * cannot carry writable globals because the patch blob is executed from MRAM. */
typedef struct
{
    uint8_t* begin;
    size_t size;
    size_t used;
} g2_h264_arena_span_t;

typedef struct
{
    g2_h264_arena_span_t spans[2];
    uint8_t active;
} g2_h264_runtime_t;

typedef enum
{
    G2_H264_REBIND_OK               = 0,
    G2_H264_REBIND_INVALID_ARGUMENT = 1,
    G2_H264_REBIND_RUNTIME_MISMATCH = 2,
    G2_H264_REBIND_USED_OVERFLOW    = 3
} g2_h264_rebind_result_t;

/* Supplied by the firmware integration. Returns NULL until the CFW singleton
 * has been created; the decoder is only started after that point. */
g2_h264_runtime_t* g2_h264_runtime_storage(void);

/* Restore the caller-owned arena description before a NAL decode. Existing
 * allocations are preserved by supplying the last captured used offsets. On
 * firmware builds the expected runtime must be the singleton returned by
 * g2_h264_runtime_storage(), preventing accidental cross-context binding. */
g2_h264_rebind_result_t g2_h264_rebind_memory(
    g2_h264_runtime_t* expected_runtime,
    const g2_h264_memory_t* external_memory,
    size_t first_used,
    size_t second_used
);

/*
 * Number of bytes and alignment required for the decoder object itself.
 * This does NOT yet include std::vector heap allocations.
 */
size_t g2_h264_decoder_size(void);
size_t g2_h264_decoder_alignment(void);

/*
 * Construct an H264Decoder in caller-owned writable RAM.
 * memory must be at least g2_h264_decoder_size() bytes and correctly aligned.
 *
 * Returns the opaque decoder handle, or NULL on invalid input.
 */
void* g2_h264_init(void* memory, size_t size);

/* Construct the decoder while routing large frame/context allocations into
 * two caller-owned spans. The spans must remain valid until destroy/reset. */
void* g2_h264_init_with_memory(
    void* memory,
    size_t size,
    const g2_h264_memory_t* external_memory
);

/* Reset an already-constructed decoder. */
void g2_h264_reset(void* decoder);

/* Destroy the decoder object. */
void g2_h264_destroy(void* decoder);

g2_h264_result_t g2_h264_decode_nal(
    void* decoder,
    const uint8_t* data,
    size_t size
);

const uint8_t* g2_h264_get_y(const void* decoder);

uint32_t g2_h264_width(const void* decoder);
uint32_t g2_h264_height(const void* decoder);
uint32_t g2_h264_y_stride(const void* decoder);
uint32_t g2_h264_frame_count(const void* decoder);
uint32_t g2_h264_dpb_frame_capacity(const void* decoder);
uint32_t g2_h264_dpb_allocated_frames(const void* decoder);
uint32_t g2_h264_dpb_allocated_bytes(const void* decoder);

uint32_t g2_h264_diag_stage(const void* decoder);
uint32_t g2_h264_diag_mb_entered(const void* decoder);
uint32_t g2_h264_diag_mb_completed(const void* decoder);
uint32_t g2_h264_diag_bit_offset(const void* decoder);

/* Allocation preflight diagnostics for the most recent NAL.
 * status: 0=not run, 1=all requested batches passed, 2=failed. */
uint32_t g2_h264_allocation_failed_tag(const void* decoder);
uint32_t g2_h264_allocation_failed_size(const void* decoder);

#ifdef __cplusplus
}
#endif
