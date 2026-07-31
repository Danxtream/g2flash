#!/usr/bin/env bun
// Detect whether the glasses are running our custom firmware, and which
// extensions it advertises.
//
// The CFW appends protobuf field 100 (a feature-token string) to the sid=0x09
// settings READ response; stock firmware never sends it. `queryCapabilities`
// does the read and parses that field. Absence => stock firmware.
//
//     bun detect-cfw.ts
//
// Expected on CFW:
//     firmware: L=2.2.4.34 R=2.2.4.34
//     CFW detected: EVENCFW/6 img576 img640 imgz rle wakelease directfb fbguard
//       contract v6, features: img576, img640, imgz, rle, wakelease, directfb, fbguard
//       img576=yes img640=yes imgz=yes rle=yes directfb=yes fbguard=yes
// Expected on stock:
//     no CFW capability field — stock firmware (or pre-caps CFW build)

import { G2Session, querySettings, queryCapabilities, hasFeature } from "g2-kit/ble";

const session = await G2Session.open();

const settings = await querySettings(session, 100);
if (settings) {
  console.log(`firmware: L=${settings.leftSoftwareVersion} R=${settings.rightSoftwareVersion}`);
}

const caps = await queryCapabilities(session, 101);
if (!caps) {
  console.log("no CFW capability field — stock firmware (or pre-caps CFW build)");
} else {
  console.log(`CFW detected: ${caps.raw}`);
  console.log(`  contract v${caps.version}, features: ${[...caps.features].join(", ")}`);
  // Example of gating behavior on individual features:
  for (const f of ["img576", "img640", "imgz", "rle", "directfb", "fbguard"]) {
    process.stdout.write(`  ${f}=${hasFeature(caps, f) ? "yes" : "no"}`);
  }
  console.log();
}

await session.close();
process.exit(0);
