import asyncio
import time
from collections import defaultdict
from bleak import BleakScanner

LEFT  = "C4:60:45:13:B3:36"
RIGHT = "C4:AF:F2:54:38:29"

SECONDS = 30.0

seen = defaultdict(list)
meta = {}


def hx(data):
    return bytes(data).hex().upper() if data is not None else ""


def callback(device, adv):
    addr = (device.address or "").upper()

    rssi = getattr(adv, "rssi", None)

    if rssi is not None:
        seen[addr].append((time.time(), rssi))

    meta[addr] = {
        "name": adv.local_name or device.name or "",
        "mfg": dict(getattr(adv, "manufacturer_data", {}) or {}),
        "svc": list(getattr(adv, "service_uuids", []) or []),
        "sdat": dict(getattr(adv, "service_data", {}) or {}),
    }


async def main():
    print()
    print("============================================================")
    print("G2 CONTINUOUS PASSIVE BLE SCAN")
    print("NO CONNECTIONS / NO READS / NO WRITES / NO FLASH")
    print("============================================================")
    print()
    print("KNOWN LEFT  =", LEFT)
    print("KNOWN RIGHT =", RIGHT)
    print()
    print(f"Listening continuously for {SECONDS:.0f} seconds...")
    print()

    scanner = BleakScanner(detection_callback=callback)

    await scanner.start()

    try:
        await asyncio.sleep(SECONDS)
    finally:
        await scanner.stop()

    print("============================================================")
    print("KNOWN GLASSES")
    print("============================================================")

    for label, addr in [("LEFT", LEFT), ("RIGHT", RIGHT)]:

        samples = seen.get(addr, [])

        if samples:
            rssis = [x[1] for x in samples]

            print(
                f"{label}: SEEN "
                f"addr={addr} "
                f"packets={len(samples)} "
                f"rssiMin={min(rssis)} "
                f"rssiMax={max(rssis)} "
                f"rssiLast={rssis[-1]}"
            )
        else:
            print(
                f"{label}: NOT SEEN addr={addr}"
            )

    print()
    print("============================================================")
    print("ALL DEVICES OBSERVED")
    print("============================================================")

    rows = []

    for addr, samples in seen.items():

        rssis = [x[1] for x in samples]
        m = meta.get(addr, {})

        rows.append((
            max(rssis),
            addr,
            len(samples),
            min(rssis),
            max(rssis),
            rssis[-1],
            m
        ))

    rows.sort(reverse=True)

    for _, addr, count, rmin, rmax, rlast, m in rows:

        print()
        print(
            f"ADDR={addr} "
            f"NAME={m.get('name','')!r} "
            f"PACKETS={count} "
            f"RSSI={rmin}..{rmax} "
            f"LAST={rlast}"
        )

        for k, v in sorted(m.get("mfg", {}).items()):
            print(
                f"  MFG 0x{k:04X}={hx(v)}"
            )

        for u in m.get("svc", []):
            print(
                f"  SVC {u}"
            )

        for k, v in m.get("sdat", {}).items():
            print(
                f"  SDAT {k}={hx(v)}"
            )

    print()
    print("============================================================")
    print("PASSIVE SCAN COMPLETE")
    print("============================================================")


asyncio.run(main())
