#include "g2_h264.h"

#include "sub0h264_config.hpp"
#include "g2_h264_runtime.hpp"
#include "sub0h264_embedded_timing.hpp"
#include "decoder.hpp"
#include "nal.hpp"

#include <cstdint>
#include <new>

using sub0h264::DecodeStatus;
using sub0h264::Frame;
using sub0h264::H264Decoder;
using sub0h264::NalUnit;
using sub0h264::parseNalUnit;

#if defined(__thumb__)
extern "C"
bool g2_h264_allocation_preflight(
    const sub0h264::AllocationRequest* requests,
    size_t count,
    sub0h264::AllocationFailure* failure) noexcept
{
    void* held[16] = {};
    size_t heldCount = 0U;
    size_t arenaSizes[16] = {};

    if (requests == nullptr || count > 16U)
    {
        if (failure != nullptr)
            *failure = {};
        return false;
    }

    for (size_t i = 0U; i < count; ++i)
        arenaSizes[i] = requests[i].size;

    const g2_h264_runtime_t* runtime = g2_h264_runtime();
    if (runtime != nullptr && runtime->active &&
        !g2_h264_runtime_can_allocate_batch(arenaSizes, count))
    {
        if (failure != nullptr)
        {
            for (size_t i = 0U; i < count; ++i)
            {
                if (requests[i].size >= G2_H264_ARENA_THRESHOLD)
                {
                    failure->tag = requests[i].tag;
                    failure->size = requests[i].size;
                    break;
                }
            }
        }
        return false;
    }

    for (size_t i = 0U; i < count; ++i)
    {
        const size_t requestSize = requests[i].size;
        if (requestSize == 0U ||
            (runtime != nullptr && runtime->active &&
             requestSize >= G2_H264_ARENA_THRESHOLD))
            continue;

        void* allocation = G2_FW_MALLOC(static_cast<uint32_t>(requestSize));
        if (allocation == nullptr)
        {
            if (failure != nullptr)
            {
                failure->tag = requests[i].tag;
                failure->size = requestSize;
            }
            while (heldCount != 0U)
                G2_FW_FREE(held[--heldCount]);
            return false;
        }

        held[heldCount++] = allocation;
    }

    while (heldCount != 0U)
        G2_FW_FREE(held[--heldCount]);

    return true;
}
#endif

struct G2H264State
{
    H264Decoder decoder;
    NalUnit nalScratch;
};

static_assert(sizeof(G2H264State) <= 4096U,
              "G2 H264 state must fit in a small firmware-heap allocation");

static H264Decoder* decoderFrom(void* state)
{
    return &static_cast<G2H264State*>(state)->decoder;
}


static const H264Decoder* decoderFrom(const void* state)
{
    return &static_cast<const G2H264State*>(state)->decoder;
}

extern "C"
size_t g2_h264_decoder_size(void)
{
    return sizeof(G2H264State);
}


extern "C"
size_t g2_h264_decoder_alignment(void)
{
    return alignof(G2H264State);
}


extern "C"
void* g2_h264_init(void* memory, size_t size)
{
    if (memory == nullptr)
        return nullptr;

    if (size < sizeof(G2H264State))
        return nullptr;

    const uintptr_t address =
        reinterpret_cast<uintptr_t>(memory);

    if ((address % alignof(G2H264State)) != 0U)
        return nullptr;

    return new (memory) G2H264State();
}


extern "C"
void* g2_h264_init_with_memory(
    void* memory,
    size_t size,
    const g2_h264_memory_t* externalMemory)
{
#if defined(__thumb__)
    if (externalMemory == nullptr || externalMemory->first == nullptr ||
        externalMemory->first_size == 0U)
        return nullptr;
    g2_h264_runtime_set_arenas(
        externalMemory->first,
        externalMemory->first_size,
        externalMemory->second,
        externalMemory->second_size);
#else
    (void)externalMemory;
#endif
    void* result = g2_h264_init(memory, size);
#if defined(__thumb__)
    if (result == nullptr)
        g2_h264_runtime_clear_arenas();
#endif
    return result;
}


extern "C"
g2_h264_rebind_result_t g2_h264_rebind_memory(
    g2_h264_runtime_t* expectedRuntime,
    const g2_h264_memory_t* externalMemory,
    size_t firstUsed,
    size_t secondUsed)
{
    if (expectedRuntime == nullptr || externalMemory == nullptr ||
        externalMemory->first == nullptr || externalMemory->first_size == 0U)
        return G2_H264_REBIND_INVALID_ARGUMENT;

#if defined(__thumb__)
    if (g2_h264_runtime() != expectedRuntime)
        return G2_H264_REBIND_RUNTIME_MISMATCH;
#endif

    if (firstUsed > externalMemory->first_size ||
        secondUsed > externalMemory->second_size)
        return G2_H264_REBIND_USED_OVERFLOW;

    expectedRuntime->spans[0] = {
        static_cast<uint8_t*>(externalMemory->first),
        externalMemory->first_size,
        firstUsed,
    };
    expectedRuntime->spans[1] = {
        static_cast<uint8_t*>(externalMemory->second),
        externalMemory->second_size,
        secondUsed,
    };
    expectedRuntime->active = true;
    return G2_H264_REBIND_OK;
}


extern "C"
void g2_h264_destroy(void* decoder)
{
    if (decoder == nullptr)
        return;

    static_cast<G2H264State*>(decoder)->~G2H264State();
#if defined(__thumb__)
    g2_h264_runtime_clear_arenas();
#endif
}


extern "C"
void g2_h264_reset(void* decoder)
{
    if (decoder == nullptr)
        return;

    G2H264State* state = static_cast<G2H264State*>(decoder);
    state->~G2H264State();
#if defined(__thumb__)
    g2_h264_runtime_reset_arenas();
#endif
    new (state) G2H264State();
}


extern "C"
g2_h264_result_t g2_h264_decode_nal(
        void* decoder,
        const uint8_t* data,
        size_t size)
{
    if (decoder == nullptr)
        return G2_H264_ERROR;

    if (data == nullptr || size == 0U)
        return G2_H264_ERROR;

    G2H264State* state =
        static_cast<G2H264State*>(decoder);
    H264Decoder* d = decoderFrom(decoder);

    /*
     * Accept any of these forms:
     *
     *   00 00 01 <NAL header + payload>
     *   00 00 00 01 <NAL header + payload>
     *   <NAL header + payload>
     *
     * Sub0h264::parseNalUnit() expects the pointer to start
     * directly at the NAL header byte.
     */

    if (size >= 4U &&
        data[0] == 0x00U &&
        data[1] == 0x00U &&
        data[2] == 0x00U &&
        data[3] == 0x01U)
    {
        data += 4U;
        size -= 4U;
    }
    else if (size >= 3U &&
             data[0] == 0x00U &&
             data[1] == 0x00U &&
             data[2] == 0x01U)
    {
        data += 3U;
        size -= 3U;
    }

    if (size == 0U)
        return G2_H264_ERROR;

    if (size > UINT32_MAX)
        return G2_H264_ERROR;

    if (!parseNalUnit(
            data,
            static_cast<uint32_t>(size),
            state->nalScratch))
    {
        return G2_H264_ERROR;
    }

    const DecodeStatus status =
            d->processNal(state->nalScratch);

    switch (status)
    {
        case DecodeStatus::FrameDecoded:
            return G2_H264_FRAME_READY;

        case DecodeStatus::NeedMoreData:
            return G2_H264_NEED_MORE_DATA;

        case DecodeStatus::Error:
        default:
            return G2_H264_ERROR;
    }
}


extern "C"
const uint8_t* g2_h264_get_y(const void* decoder)
{
    if (decoder == nullptr)
        return nullptr;

    const H264Decoder* d = decoderFrom(decoder);

    const Frame* frame =
            d->currentFrame();

    if (frame == nullptr)
        return nullptr;

    return frame->yData();
}


extern "C"
uint32_t g2_h264_width(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;

    const H264Decoder* d = decoderFrom(decoder);

    const Frame* frame =
            d->currentFrame();

    if (frame == nullptr)
        return 0U;

    return frame->width();
}


extern "C"
uint32_t g2_h264_height(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;

    const H264Decoder* d = decoderFrom(decoder);

    const Frame* frame =
            d->currentFrame();

    if (frame == nullptr)
        return 0U;

    return frame->height();
}


extern "C"
uint32_t g2_h264_y_stride(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;

    const H264Decoder* d = decoderFrom(decoder);

    const Frame* frame =
            d->currentFrame();

    if (frame == nullptr)
        return 0U;

    return frame->yStride();
}


extern "C"
uint32_t g2_h264_frame_count(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;

    const H264Decoder* d = decoderFrom(decoder);

    return d->frameCount();
}


extern "C"
uint32_t g2_h264_dpb_frame_capacity(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;

    const H264Decoder* d = decoderFrom(decoder);

    return d->dpbFrameCapacity();
}


extern "C"
uint32_t g2_h264_dpb_allocated_frames(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;

    const H264Decoder* d = decoderFrom(decoder);

    return d->dpbAllocatedFrameCount();
}


extern "C"
uint32_t g2_h264_dpb_allocated_bytes(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;

    const H264Decoder* d = decoderFrom(decoder);

    return d->dpbAllocatedFrameBytes();
}

extern "C"
uint32_t g2_h264_diag_stage(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;

    return decoderFrom(decoder)->diagStage();
}

extern "C"
uint32_t g2_h264_diag_mb_entered(const void* decoder)
{
    if (decoder == nullptr)
        return UINT32_MAX;

    return decoderFrom(decoder)->diagMbEntered();
}

extern "C"
uint32_t g2_h264_diag_mb_completed(const void* decoder)
{
    if (decoder == nullptr)
        return UINT32_MAX;

    return decoderFrom(decoder)->diagMbCompleted();
}

extern "C"
uint32_t g2_h264_diag_bit_offset(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;

    return decoderFrom(decoder)->diagBitOffset();
}

extern "C"
uint32_t g2_h264_allocation_failed_tag(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;
    return decoderFrom(decoder)->allocationFailedTag();
}

extern "C"
uint32_t g2_h264_allocation_failed_size(const void* decoder)
{
    if (decoder == nullptr)
        return 0U;
    return decoderFrom(decoder)->allocationFailedSize();
}
