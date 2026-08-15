#pragma once

#include <cstddef>
#include <cstdint>

#if defined(__thumb__)

using g2_fw_malloc_fn = void* (*)(uint32_t);
using g2_fw_free_fn   = void  (*)(void*);

#define G2_FW_MALLOC ((g2_fw_malloc_fn)0x00474cd3U)
#define G2_FW_FREE   ((g2_fw_free_fn)0x00474d17U)

/*
 * Large Sub0h264 vectors are placed in two caller-owned spans while video is
 * active.  Small STL bookkeeping allocations still use the firmware heap so
 * temporary reference-list vectors can be freed normally.  The 2 KiB cutoff
 * covers every frame plane plus the large per-picture context arrays.
 */
inline constexpr size_t G2_H264_ARENA_THRESHOLD = 2048U;
inline constexpr size_t G2_H264_ARENA_ALIGNMENT = 8U;

inline g2_h264_runtime_t* g2_h264_runtime() noexcept
{
    return g2_h264_runtime_storage();
}

inline size_t g2_h264_align_up(size_t value) noexcept
{
    return (value + G2_H264_ARENA_ALIGNMENT - 1U) &
           ~(G2_H264_ARENA_ALIGNMENT - 1U);
}

inline void g2_h264_runtime_set_arenas(
    void* first, size_t firstSize,
    void* second, size_t secondSize) noexcept
{
    g2_h264_runtime_t* runtime = g2_h264_runtime();
    if (runtime == nullptr)
        return;
    runtime->spans[0] = {
        static_cast<unsigned char*>(first), firstSize, 0U
    };
    runtime->spans[1] = {
        static_cast<unsigned char*>(second), secondSize, 0U
    };
    runtime->active = first != nullptr && firstSize != 0U;
}

inline void g2_h264_runtime_reset_arenas() noexcept
{
    g2_h264_runtime_t* runtime = g2_h264_runtime();
    if (runtime == nullptr)
        return;
    runtime->spans[0].used = 0U;
    runtime->spans[1].used = 0U;
}

inline void g2_h264_runtime_clear_arenas() noexcept
{
    g2_h264_runtime_t* runtime = g2_h264_runtime();
    if (runtime == nullptr)
        return;
    runtime->active = false;
    runtime->spans[0] = {};
    runtime->spans[1] = {};
}

inline bool g2_h264_runtime_contains(const void* ptr) noexcept
{
    const g2_h264_runtime_t* runtime = g2_h264_runtime();
    if (runtime == nullptr)
        return false;
    const auto* p = static_cast<const unsigned char*>(ptr);
    for (const auto& span : runtime->spans)
    {
        if (span.begin != nullptr && p >= span.begin && p < span.begin + span.size)
            return true;
    }
    return false;
}

inline void* g2_h264_runtime_arena_allocate(size_t size) noexcept
{
    g2_h264_runtime_t* runtime = g2_h264_runtime();
    if (runtime == nullptr || !runtime->active)
        return nullptr;
    const size_t alignedSize = g2_h264_align_up(size);
    for (auto& span : runtime->spans)
    {
        const size_t offset = g2_h264_align_up(span.used);
        if (span.begin != nullptr && offset <= span.size &&
            alignedSize <= span.size - offset)
        {
            void* result = span.begin + offset;
            span.used = offset + alignedSize;
            return result;
        }
    }
    return nullptr;
}

inline bool g2_h264_runtime_can_allocate_batch(
    const size_t* sizes, size_t count) noexcept
{
    const g2_h264_runtime_t* runtime = g2_h264_runtime();
    if (runtime == nullptr || !runtime->active)
        return false;
    size_t used[2] = {
        runtime->spans[0].used,
        runtime->spans[1].used,
    };
    for (size_t i = 0U; i < count; ++i)
    {
        if (sizes[i] < G2_H264_ARENA_THRESHOLD)
            continue;
        const size_t alignedSize = g2_h264_align_up(sizes[i]);
        bool placed = false;
        for (size_t s = 0U; s < 2U; ++s)
        {
            const auto& span = runtime->spans[s];
            const size_t offset = g2_h264_align_up(used[s]);
            if (span.begin != nullptr && offset <= span.size &&
                alignedSize <= span.size - offset)
            {
                used[s] = offset + alignedSize;
                placed = true;
                break;
            }
        }
        if (!placed)
            return false;
    }
    return true;
}

void* operator new(size_t size)
{
    void* p = nullptr;
    const g2_h264_runtime_t* runtime = g2_h264_runtime();
    if (runtime != nullptr && runtime->active &&
        size >= G2_H264_ARENA_THRESHOLD)
        p = g2_h264_runtime_arena_allocate(size);
    else
        p = G2_FW_MALLOC(static_cast<uint32_t>(size));

    if (p == nullptr)
    {
        __builtin_trap();
    }

    return p;
}

void operator delete(void* ptr) noexcept
{
    if (ptr != nullptr && !g2_h264_runtime_contains(ptr))
        G2_FW_FREE(ptr);
}

void operator delete(void* ptr, size_t) noexcept
{
    if (ptr != nullptr && !g2_h264_runtime_contains(ptr))
        G2_FW_FREE(ptr);
}

namespace std
{

[[noreturn]] void __throw_bad_alloc()
{
    __builtin_trap();
}

[[noreturn]] void __throw_bad_array_new_length()
{
    __builtin_trap();
}

[[noreturn]] void __throw_length_error(const char*)
{
    __builtin_trap();
}

} // namespace std

extern "C" __attribute__((noinline, used))
void* memcpy(void* destination, const void* source, size_t size)
{
    auto* out = static_cast<volatile unsigned char*>(destination);
    const auto* in = static_cast<const volatile unsigned char*>(source);

    for (size_t i = 0; i < size; ++i)
        out[i] = in[i];

    return destination;
}

extern "C" __attribute__((noinline, used))
void* memset(void* destination, int value, size_t size)
{
    auto* out = static_cast<volatile unsigned char*>(destination);
    const auto byte = static_cast<unsigned char>(value);

    for (size_t i = 0; i < size; ++i)
        out[i] = byte;

    return destination;
}

extern "C" __attribute__((noinline, used))
void* memmove(void* destination, const void* source, size_t size)
{
    auto* out = static_cast<volatile unsigned char*>(destination);
    const auto* in = static_cast<const volatile unsigned char*>(source);

    if (out < in)
    {
        for (size_t i = 0; i < size; ++i)
            out[i] = in[i];
    }
    else if (out > in)
    {
        while (size != 0U)
        {
            --size;
            out[size] = in[size];
        }
    }

    return destination;
}

extern "C" __attribute__((noinline, used))
int abs(int value)
{
    return value < 0 ? -value : value;
}

extern "C" __attribute__((noinline, used))
void __aeabi_memcpy(void* destination, const void* source, size_t size) noexcept
{
    memcpy(destination, source, size);
}

extern "C" __attribute__((noinline, used))
void __aeabi_memcpy4(void* destination, const void* source, size_t size) noexcept
{
    memcpy(destination, source, size);
}

extern "C" __attribute__((noinline, used))
void __aeabi_memmove(void* destination, const void* source, size_t size) noexcept
{
    memmove(destination, source, size);
}

extern "C" __attribute__((noinline, used))
void __aeabi_memmove4(void* destination, const void* source, size_t size) noexcept
{
    memmove(destination, source, size);
}

extern "C" __attribute__((noinline, used))
void __aeabi_memclr(void* destination, size_t size) noexcept
{
    memset(destination, 0, size);
}

extern "C" __attribute__((noinline, used))
void __aeabi_memclr4(void* destination, size_t size) noexcept
{
    memset(destination, 0, size);
}

extern "C" __attribute__((noinline, used))
void __aeabi_memset(void* destination, size_t size, int value) noexcept
{
    memset(destination, value, size);
}

#endif // defined(__thumb__)
