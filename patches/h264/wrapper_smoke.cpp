#include "g2_h264.h"

#include "annexb.hpp"

#include <cstdlib>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <vector>

int main(int argc, char** argv)
{
    const char* path = argc > 1
            ? argv[1]
            : R"(C:\Users\danxt\Desktop\G2 Video player project\g2_10s_700k.h264)";
    const uint32_t expectedFrames = argc > 2
            ? static_cast<uint32_t>(std::strtoul(argv[2], nullptr, 10))
            : 300U;
    const uint32_t expectedWidth = argc > 3
            ? static_cast<uint32_t>(std::strtoul(argv[3], nullptr, 10))
            : 320U;
    const uint32_t expectedHeight = argc > 4
            ? static_cast<uint32_t>(std::strtoul(argv[4], nullptr, 10))
            : 192U;
    const uint32_t expectedDpbFrames = argc > 5
            ? static_cast<uint32_t>(std::strtoul(argv[5], nullptr, 10))
            : 0U;
    const uint32_t repeatCount = argc > 6
            ? static_cast<uint32_t>(std::strtoul(argv[6], nullptr, 10))
            : 1U;

    if (repeatCount == 0U)
    {
        std::cerr << "Repeat count must be at least one\n";
        return 1;
    }

    std::ifstream file(path, std::ios::binary | std::ios::ate);

    if (!file)
    {
        std::cerr << "Could not open test stream\n";
        return 1;
    }

    const std::streamsize fileSize = file.tellg();

    if (fileSize <= 0)
    {
        std::cerr << "Test stream is empty\n";
        return 1;
    }

    file.seekg(0, std::ios::beg);

    std::vector<uint8_t> data(
            static_cast<size_t>(fileSize)
    );

    if (!file.read(
            reinterpret_cast<char*>(data.data()),
            fileSize))
    {
        std::cerr << "Could not read test stream\n";
        return 1;
    }

    if (data.size() > UINT32_MAX)
    {
        std::cerr << "Test stream is too large\n";
        return 1;
    }

    const size_t decoderSize = g2_h264_decoder_size();
    const size_t decoderAlignment = g2_h264_decoder_alignment();

    // The firmware restores this bookkeeping immediately before every NAL.
    // Exercise the same reconstruction path without requiring the ARM target.
    uint8_t firstArena[128] = {};
    uint8_t secondArena[64] = {};
    g2_h264_runtime_t runtime = {};
    const g2_h264_memory_t externalMemory = {
        firstArena, sizeof(firstArena), secondArena, sizeof(secondArena),
    };
    if (g2_h264_rebind_memory(&runtime, &externalMemory, 48U, 24U) !=
            G2_H264_REBIND_OK ||
        !runtime.active || runtime.spans[0].begin != firstArena ||
        runtime.spans[0].size != sizeof(firstArena) ||
        runtime.spans[0].used != 48U ||
        runtime.spans[1].begin != secondArena ||
        runtime.spans[1].size != sizeof(secondArena) ||
        runtime.spans[1].used != 24U)
    {
        std::cerr << "Arena rebind smoke failed\n";
        return 1;
    }
    if (g2_h264_rebind_memory(
            &runtime,
            &externalMemory,
            sizeof(firstArena) + 1U,
            24U
        ) != G2_H264_REBIND_USED_OVERFLOW ||
        runtime.spans[0].used != 48U || runtime.spans[1].used != 24U)
    {
        std::cerr << "Arena rebind overflow guard failed\n";
        return 1;
    }
    if (g2_h264_rebind_memory(nullptr, &externalMemory, 0U, 0U) !=
        G2_H264_REBIND_INVALID_ARGUMENT)
    {
        std::cerr << "Arena rebind argument guard failed\n";
        return 1;
    }

    std::vector<uint8_t> decoderStorage(
            decoderSize + decoderAlignment - 1U
    );

    const uintptr_t storageAddress =
            reinterpret_cast<uintptr_t>(decoderStorage.data());

    const uintptr_t alignedAddress =
            (storageAddress + decoderAlignment - 1U)
            & ~(static_cast<uintptr_t>(decoderAlignment) - 1U);

    void* decoder = g2_h264_init(
            reinterpret_cast<void*>(alignedAddress),
            decoderSize
    );

    if (decoder == nullptr)
    {
        std::cerr << "Decoder init failed\n";
        return 1;
    }

    struct DecoderGuard
    {
        void* decoder;

        ~DecoderGuard()
        {
            g2_h264_destroy(decoder);
        }
    } decoderGuard{decoder};

    std::vector<sub0h264::NalBounds> nals;

    sub0h264::findNalUnits(
            data.data(),
            static_cast<uint32_t>(data.size()),
            nals
    );

    std::cout << "NALs found: " << nals.size() << '\n';

    if (nals.empty())
    {
        std::cerr << "No NAL units found\n";
        return 1;
    }

    uint32_t totalFramesReady = 0U;
    uint32_t totalErrors = 0U;
    uint32_t totalNeedMoreData = 0U;

    for (uint32_t pass = 0U; pass < repeatCount; ++pass)
    {
        if (pass != 0U)
            g2_h264_reset(decoder);

        uint32_t passFramesReady = 0U;
        uint32_t passErrors = 0U;
        uint32_t passNeedMoreData = 0U;

        for (const sub0h264::NalBounds& bounds : nals)
        {
            const g2_h264_result_t result =
                    g2_h264_decode_nal(
                            decoder,
                            data.data() + bounds.offset,
                            bounds.size
                    );

            switch (result)
            {
                case G2_H264_FRAME_READY:
                    ++passFramesReady;
                    break;

                case G2_H264_NEED_MORE_DATA:
                    ++passNeedMoreData;
                    break;

                case G2_H264_ERROR:
                default:
                    ++passErrors;
                    break;
            }
        }

        std::cout
                << "Pass " << (pass + 1U) << '/' << repeatCount
                << ": frames=" << passFramesReady
                << " need=" << passNeedMoreData
                << " errors=" << passErrors << '\n';

        if (passFramesReady != expectedFrames || passErrors != 0U)
        {
            std::cerr << "FAIL: decode pass did not meet expectations\n";
            return 2;
        }

        totalFramesReady += passFramesReady;
        totalErrors += passErrors;
        totalNeedMoreData += passNeedMoreData;
    }

    std::cout
            << "Frames ready: " << totalFramesReady << '\n'
            << "Decoder frame count: " << g2_h264_frame_count(decoder) << '\n'
            << "Need more data: " << totalNeedMoreData << '\n'
            << "Errors: " << totalErrors << '\n'
            << "Width: " << g2_h264_width(decoder) << '\n'
            << "Height: " << g2_h264_height(decoder) << '\n'
            << "Y stride: " << g2_h264_y_stride(decoder) << '\n'
            << "DPB frames: " << g2_h264_dpb_allocated_frames(decoder)
            << '/' << g2_h264_dpb_frame_capacity(decoder) << '\n'
            << "DPB bytes: " << g2_h264_dpb_allocated_bytes(decoder) << '\n'
            << "Y ptr: "
            << static_cast<const void*>(g2_h264_get_y(decoder))
            << '\n';

    if (totalFramesReady != expectedFrames * repeatCount)
    {
        std::cerr
                << "FAIL: expected " << (expectedFrames * repeatCount)
                << " frame-ready results\n";
        return 2;
    }

    if (g2_h264_frame_count(decoder) != expectedFrames)
    {
        std::cerr
                << "FAIL: decoder frame count is not "
                << expectedFrames << '\n';
        return 3;
    }

    if (totalErrors != 0U)
    {
        std::cerr << "FAIL: decoder reported errors\n";
        return 4;
    }

    if (g2_h264_width(decoder) != expectedWidth)
    {
        std::cerr
                << "FAIL: width is not " << expectedWidth << '\n';
        return 5;
    }

    if (g2_h264_height(decoder) != expectedHeight)
    {
        std::cerr
                << "FAIL: height is not " << expectedHeight << '\n';
        return 6;
    }

    if (g2_h264_get_y(decoder) == nullptr)
    {
        std::cerr << "FAIL: Y plane is null\n";
        return 7;
    }

    if (g2_h264_y_stride(decoder) < g2_h264_width(decoder))
    {
        std::cerr << "FAIL: invalid Y stride\n";
        return 8;
    }

    if (expectedDpbFrames != 0U)
    {
        if (g2_h264_dpb_allocated_frames(decoder) != expectedDpbFrames ||
            g2_h264_dpb_frame_capacity(decoder) != expectedDpbFrames)
        {
            std::cerr
                    << "FAIL: expected DPB " << expectedDpbFrames
                    << '/' << expectedDpbFrames << '\n';
            return 9;
        }

        const uint32_t expectedDpbBytes =
                expectedWidth * expectedHeight * 3U / 2U * expectedDpbFrames;

        if (g2_h264_dpb_allocated_bytes(decoder) != expectedDpbBytes)
        {
            std::cerr
                    << "FAIL: expected " << expectedDpbBytes
                    << " DPB bytes\n";
            return 10;
        }
    }

    std::cout << "G2 H264 wrapper smoke test PASSED\n";

    return 0;
}
