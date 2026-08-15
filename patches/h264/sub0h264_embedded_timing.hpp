#pragma once

/*
 * decoder.hpp includes the upstream timing header even in non-timing builds,
 * and its optional runtime profile hooks still reference the desktop clock.
 * Supply the small API decoder.hpp needs without pulling in std::chrono.
 */
#ifndef CROG_SUB0H264_DECODE_TIMING_HPP
#define CROG_SUB0H264_DECODE_TIMING_HPP

#include <cstdint>

inline constexpr int64_t sub0h264TimerUs() noexcept
{
    return 0;
}

namespace sub0h264
{

struct SectionProfile
{
    int64_t entropyUs = 0;
    int64_t intraPredUs = 0;
    int64_t interPredUs = 0;
    int64_t transformUs = 0;
    int64_t deblockUs = 0;
    int64_t overheadUs = 0;
    uint32_t frameCount = 0U;
};

} // namespace sub0h264

#endif // CROG_SUB0H264_DECODE_TIMING_HPP
