#pragma once

/*
 * G2-specific Sub0h264 configuration.
 *
 * Embedded configuration and feature switches should live here
 * instead of modifying upstream Sub0h264 where possible.
 */

#ifndef SUB0H264_TRACE
#define SUB0H264_TRACE 0
#endif

/*
 * Faceclaw's video pipeline accepts a constrained stream with one SPS and one
 * PPS, both using ID 0. Keeping the spec-sized 32/256 tables inside every
 * decoder instance costs more than 142 KiB of contiguous firmware heap.
 */
#ifndef SUB0H264_MAX_SPS_COUNT
#define SUB0H264_MAX_SPS_COUNT 1U
#endif

#ifndef SUB0H264_MAX_PPS_COUNT
#define SUB0H264_MAX_PPS_COUNT 1U
#endif

/* The DPB already owns the current decoded frame used by the G2 wrapper. */
#ifndef SUB0H264_DISABLE_LEGACY_CURRENT_FRAME
#define SUB0H264_DISABLE_LEGACY_CURRENT_FRAME 1
#endif

/* Reserve each decoder allocation batch with the firmware allocator before
 * std::vector reaches operator new. This turns predictable firmware-heap OOM
 * into a reported decode error instead of the runtime's hard trap. */
#if defined(__thumb__) && !defined(SUB0H264_ALLOCATION_PREFLIGHT)
#define SUB0H264_ALLOCATION_PREFLIGHT g2_h264_allocation_preflight
#endif
