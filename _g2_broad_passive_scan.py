import asyncio
from datetime import datetime
from bleak import BleakScanner

LEFT_ADDR = "C4:60:45:13:B3:36".upper()
SCAN_SECONDS = 30.0


def hx(data):
    if data is None:
        return ""
    return bytes(data).hex().upper()


def record(addr, dev, adv):
    return {
        "addr": addr.upper(),
        "name": adv.local_name or dev.name or "",
        "rssi": getattr(adv, "rssi", None),
        "tx": getattr(adv, "tx_power", None),
        "mfg": dict(getattr(adv, "manufacturer_data", {}) or {}),
        "svc_uuids": list(getattr(adv, "service_uuids", []) or []),
        "svc_data": dict(getattr(adv, "service_data", {}) or {}),
    }


async def main():
    print()
    print("============================================================")
    print("G2 BROAD BLE ADVERTISEMENT SCAN")
    print("NO CONNECTIONS / NO GATT READS / NO GATT WRITES / NO FLASH")
    print("============================================================")
    print(f"START = {datetime.now().isoformat(timespec='seconds')}")
    print()

    found = await BleakScanner.discover(
        timeout=SCAN_SECONDS,
        return_adv=True
    )

    rows = [
        record(addr, dev, adv)
        for addr, (dev, adv) in found.items()
    ]

    rows.sort(key=lambda x: (
        0 if x["addr"] == LEFT_ADDR else 1,
        x["name"].lower(),
        x["addr"]
    ))

    left = next(
        (x for x in rows if x["addr"] == LEFT_ADDR),
        None
    )

    if left:
        left_mfg = set(left["mfg"].keys())
        left_svc = {x.lower() for x in left["svc_uuids"]}
        left_sd  = {x.lower() for x in left["svc_data"].keys()}
    else:
        left_mfg = set()
        left_svc = set()
        left_sd  = set()

    print(f"TOTAL DEVICES = {len(rows)}")
    print()

    if left:
        print("---------------- KNOWN LEFT FINGERPRINT ----------------")
        print(f"ADDR = {left['addr']}")
        print(f"NAME = {left['name']!r}")
        print(f"RSSI = {left['rssi']}")
        print(f"TX   = {left['tx']}")

        for k, v in sorted(left["mfg"].items()):
            print(f"MFG  0x{k:04X} = {hx(v)}")

        for u in left["svc_uuids"]:
            print(f"SVC  = {u}")

        for k, v in left["svc_data"].items():
            print(f"SDAT {k} = {hx(v)}")

        print()
    else:
        print("WARNING: known LEFT was not seen during this scan.")
        print()

    candidates = []

    for r in rows:
        if r["addr"] == LEFT_ADDR:
            continue

        name_l = r["name"].lower()

        g2_name = (
            "even" in name_l or
            "g2_" in name_l or
            "g1_" in name_l
        )

        shared_mfg = left_mfg.intersection(r["mfg"].keys())
        shared_svc = left_svc.intersection(
            x.lower() for x in r["svc_uuids"]
        )
        shared_sd = left_sd.intersection(
            x.lower() for x in r["svc_data"].keys()
        )

        score = 0
        reasons = []

        if g2_name:
            score += 100
            reasons.append("NAME")

        if shared_mfg:
            score += 20 * len(shared_mfg)
            reasons.append(
                "MFG=" +
                ",".join(f"0x{x:04X}" for x in sorted(shared_mfg))
            )

        if shared_svc:
            score += 20 * len(shared_svc)
            reasons.append("SERVICE_UUID")

        if shared_sd:
            score += 20 * len(shared_sd)
            reasons.append("SERVICE_DATA_UUID")

        if score:
            candidates.append((score, reasons, r))

    candidates.sort(
        key=lambda x: (-x[0], x[2]["addr"])
    )

    print("============================================================")
    print("POSSIBLE G2 / LEFT-FINGERPRINT MATCHES")
    print("============================================================")

    if not candidates:
        print("NONE")
    else:
        for score, reasons, r in candidates:
            print()
            print(
                f"CANDIDATE score={score} "
                f"reason={';'.join(reasons)}"
            )
            print(f"  ADDR = {r['addr']}")
            print(f"  NAME = {r['name']!r}")
            print(f"  RSSI = {r['rssi']}")
            print(f"  TX   = {r['tx']}")

            for k, v in sorted(r["mfg"].items()):
                print(f"  MFG  0x{k:04X} = {hx(v)}")

            for u in r["svc_uuids"]:
                print(f"  SVC  = {u}")

            for k, v in r["svc_data"].items():
                print(f"  SDAT {k} = {hx(v)}")

    print()
    print("============================================================")
    print("ALL ADVERTISING DEVICES")
    print("============================================================")

    for r in rows:
        print()
        print(
            f"ADDR={r['addr']} "
            f"NAME={r['name']!r} "
            f"RSSI={r['rssi']} "
            f"TX={r['tx']}"
        )

        if r["mfg"]:
            print(
                "  MFG=" +
                " | ".join(
                    f"0x{k:04X}:{hx(v)}"
                    for k, v in sorted(r["mfg"].items())
                )
            )

        if r["svc_uuids"]:
            print(
                "  SVC=" +
                ",".join(r["svc_uuids"])
            )

        if r["svc_data"]:
            print(
                "  SDAT=" +
                " | ".join(
                    f"{k}:{hx(v)}"
                    for k, v in r["svc_data"].items()
                )
            )

    print()
    print("============================================================")
    print("SCAN COMPLETE - STILL NO CONNECTIONS OR WRITES")
    print("============================================================")


asyncio.run(main())
