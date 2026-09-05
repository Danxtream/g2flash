import asyncio
import time
from bleak import BleakScanner

LEFT  = "C4:60:45:13:B3:36"
RIGHT = "C4:AF:F2:54:38:29"

DFU_NAMES = (
    "B210_DFU",
)

DFU_UUIDS = {
    "8ec90000-f315-4f60-9fb8-838830daea50",
    "0000fe59-0000-1000-8000-00805f9b34fb",
    "da2e7828-fbce-4e01-ae9e-261174997c48",
}

START = time.monotonic()
events = []
all_seen = {}


def hx(x):
    return bytes(x).hex().upper() if x is not None else ""


def callback(device, adv):
    now = time.monotonic() - START
    addr = (device.address or "").upper()
    name = adv.local_name or device.name or ""

    mfg = dict(
        getattr(adv, "manufacturer_data", {}) or {}
    )

    svc = {
        x.lower()
        for x in (
            getattr(adv, "service_uuids", []) or []
        )
    }

    sdat = {
        k.lower(): v
        for k, v in dict(
            getattr(adv, "service_data", {}) or {}
        ).items()
    }

    rssi = getattr(adv, "rssi", None)

    all_seen[addr] = {
        "time": now,
        "name": name,
        "rssi": rssi,
        "mfg": mfg,
        "svc": svc,
        "sdat": sdat,
    }

    reasons = []

    if addr == LEFT:
        reasons.append("KNOWN_LEFT")

    if addr == RIGHT:
        reasons.append("KNOWN_RIGHT")

    if any(x.lower() in name.lower() for x in DFU_NAMES):
        reasons.append("B210_DFU_NAME")

    if "even" in name.lower() or "g2_" in name.lower():
        reasons.append("G2_NAME")

    if 0x5245 in mfg:
        reasons.append("EVEN_MFG_5245")

    if svc & DFU_UUIDS:
        reasons.append(
            "DFU_SERVICE=" +
            ",".join(sorted(svc & DFU_UUIDS))
        )

    if set(sdat) & DFU_UUIDS:
        reasons.append(
            "DFU_SERVICE_DATA=" +
            ",".join(sorted(set(sdat) & DFU_UUIDS))
        )

    if reasons:
        events.append(
            (
                now,
                addr,
                name,
                rssi,
                reasons,
                mfg,
                svc,
                sdat,
            )
        )

        print(
            f"{now:8.3f}s "
            f"ADDR={addr} "
            f"NAME={name!r} "
            f"RSSI={rssi} "
            f"REASON={';'.join(reasons)}",
            flush=True
        )


async def main():
    print()
    print("============================================================")
    print("G2 BOOT / RECOVERY PASSIVE WATCH")
    print("NO CONNECTIONS / NO READS / NO WRITES / NO FLASH")
    print("============================================================")
    print()
    print("KNOWN LEFT  =", LEFT)
    print("KNOWN RIGHT =", RIGHT)
    print()
    print("Listening for 90 seconds.")
    print()
    print("NOW perform the case restart ONCE while this is running:")
    print("  glasses seated")
    print("  case powered")
    print("  unplug/replug power 3 times within 7 seconds")
    print("  then leave power connected")
    print()
    print("Do not start Even, Faceclaw, or any flasher.")
    print()

    scanner = BleakScanner(
        detection_callback=callback
    )

    await scanner.start()

    try:
        await asyncio.sleep(90)
    finally:
        await scanner.stop()

    print()
    print("============================================================")
    print("RESULT")
    print("============================================================")

    right_events = [
        e for e in events
        if e[1] == RIGHT
    ]

    dfu_events = [
        e for e in events
        if (
            "B210_DFU_NAME" in e[4]
            or any(
                r.startswith("DFU_")
                for r in e[4]
            )
        )
    ]

    even_events = [
        e for e in events
        if (
            "G2_NAME" in e[4]
            or "EVEN_MFG_5245" in e[4]
        )
    ]

    print(
        f"KNOWN_RIGHT_PACKETS = {len(right_events)}"
    )
    print(
        f"DFU_PACKETS         = {len(dfu_events)}"
    )
    print(
        f"EVEN_G2_PACKETS     = {len(even_events)}"
    )

    print()
    print("---------------- RIGHT ----------------")

    if right_events:
        for e in right_events:
            print(
                f"{e[0]:8.3f}s "
                f"{e[1]} "
                f"{e[2]!r} "
                f"RSSI={e[3]}"
            )
    else:
        print("NO PACKETS FROM KNOWN RIGHT ADDRESS")

    print()
    print("---------------- DFU ----------------")

    if dfu_events:
        for e in dfu_events:
            print(
                f"{e[0]:8.3f}s "
                f"ADDR={e[1]} "
                f"NAME={e[2]!r} "
                f"RSSI={e[3]} "
                f"REASON={';'.join(e[4])}"
            )
    else:
        print("NO B210/DFU ADVERTISEMENT OBSERVED")

    print()
    print("============================================================")
    print("PASSIVE WATCH COMPLETE")
    print("============================================================")


asyncio.run(main())
