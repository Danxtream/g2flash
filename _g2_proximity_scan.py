import asyncio
import statistics
from bleak import BleakScanner

LEFT  = "C4:60:45:13:B3:36"
RIGHT = "C4:AF:F2:54:38:29"

ROUNDS = 3
SECONDS = 5.0


def hx(data):
    if data is None:
        return ""
    return bytes(data).hex().upper()


async def scan_once():
    devs = await BleakScanner.discover(
        timeout=SECONDS,
        return_adv=True
    )

    out = {}

    for addr, (dev, adv) in devs.items():
        addr = addr.upper()

        rssi = getattr(adv, "rssi", None)

        out[addr] = {
            "rssi": rssi,
            "name": adv.local_name or dev.name or "",
            "mfg": dict(
                getattr(adv, "manufacturer_data", {}) or {}
            ),
            "svc": list(
                getattr(adv, "service_uuids", []) or []
            ),
            "sdat": dict(
                getattr(adv, "service_data", {}) or {}
            ),
        }

    return out


async def phase(label):
    print()
    print("============================================================")
    print(label)
    print("============================================================")

    merged = {}

    for i in range(ROUNDS):
        print(f"scan {i + 1}/{ROUNDS} ...")

        rows = await scan_once()

        for addr, r in rows.items():

            if addr not in merged:
                merged[addr] = {
                    "rssis": [],
                    "name": r["name"],
                    "mfg": r["mfg"],
                    "svc": r["svc"],
                    "sdat": r["sdat"],
                }

            if r["rssi"] is not None:
                merged[addr]["rssis"].append(r["rssi"])

            if r["name"]:
                merged[addr]["name"] = r["name"]

            if r["mfg"]:
                merged[addr]["mfg"] = r["mfg"]

            if r["svc"]:
                merged[addr]["svc"] = r["svc"]

            if r["sdat"]:
                merged[addr]["sdat"] = r["sdat"]

    result = {}

    for addr, r in merged.items():

        if not r["rssis"]:
            continue

        result[addr] = {
            **r,
            "median": statistics.median(r["rssis"]),
        }

    return result


def details(r):
    parts = []

    if r["mfg"]:
        parts.append(
            "MFG=" +
            "|".join(
                f"0x{k:04X}:{hx(v)}"
                for k, v in sorted(r["mfg"].items())
            )
        )

    if r["svc"]:
        parts.append(
            "SVC=" + ",".join(r["svc"])
        )

    if r["sdat"]:
        parts.append(
            "SDAT=" +
            "|".join(
                f"{k}:{hx(v)}"
                for k, v in r["sdat"].items()
            )
        )

    return " ".join(parts)


async def main():

    print()
    print("============================================================")
    print("G2 PASSIVE PROXIMITY CORRELATION")
    print("NO CONNECTIONS / NO READS / NO WRITES / NO FLASH")
    print("============================================================")
    print()
    print("KNOWN LEFT  =", LEFT)
    print("KNOWN RIGHT =", RIGHT)
    print()
    print("Place the glasses CLOSE to the PC now.")
    input("Press ENTER when ready... ")

    near = await phase("PHASE A - GLASSES NEAR")

    print()
    print("Now move the glasses FAR AWAY from the PC.")
    print("Do NOT place them in the charging case.")
    print("Use the far side of the room if possible.")
    input("Press ENTER when they are far away... ")

    far = await phase("PHASE B - GLASSES FAR")

    print()
    print("============================================================")
    print("KNOWN ADDRESS RESULT")
    print("============================================================")

    print(
        "LEFT  seen near/far =",
        LEFT in near,
        "/",
        LEFT in far
    )

    print(
        "RIGHT seen near/far =",
        RIGHT in near,
        "/",
        RIGHT in far
    )

    if LEFT not in near or LEFT not in far:
        print()
        print("STOP: LEFT was not measured in both phases.")
        print("The proximity comparison is not valid.")
        return

    left_near = near[LEFT]["median"]
    left_far  = far[LEFT]["median"]
    left_delta = left_far - left_near

    print()
    print("============================================================")
    print("LEFT REFERENCE")
    print("============================================================")
    print(f"LEFT near median = {left_near} dBm")
    print(f"LEFT far median  = {left_far} dBm")
    print(f"LEFT delta       = {left_delta:+.1f} dB")

    if abs(left_delta) < 10:
        print()
        print("WARNING: movement did not change LEFT RSSI enough.")
        print("Repeat with a larger distance before trusting candidates.")

    candidates = []

    for addr in sorted(set(near) & set(far)):

        if addr == LEFT:
            continue

        n = near[addr]["median"]
        f = far[addr]["median"]
        delta = f - n

        tracking_error = abs(delta - left_delta)

        candidates.append(
            (
                tracking_error,
                -n,
                addr,
                n,
                f,
                delta,
                near[addr],
            )
        )

    candidates.sort()

    print()
    print("============================================================")
    print("DEVICES WHOSE RSSI MOVED MOST LIKE THE GLASSES")
    print("============================================================")

    shown = 0

    for err, negnear, addr, n, f, delta, r in candidates:

        if err > 12:
            continue

        shown += 1

        print()
        print(
            f"CANDIDATE {shown}: "
            f"ADDR={addr} "
            f"NAME={r['name']!r}"
        )
        print(
            f"  near={n} dBm "
            f"far={f} dBm "
            f"delta={delta:+.1f} dB "
            f"trackingError={err:.1f} dB"
        )

        d = details(r)

        if d:
            print(" ", d)

    if shown == 0:
        print("NONE")

    print()
    print("============================================================")
    print("TOP 10 COMPARISON")
    print("============================================================")

    for err, negnear, addr, n, f, delta, r in candidates[:10]:
        print(
            f"{addr} "
            f"near={n:>5} "
            f"far={f:>5} "
            f"delta={delta:+6.1f} "
            f"error={err:5.1f} "
            f"name={r['name']!r}"
        )

    print()
    print("============================================================")
    print("PASSIVE TEST COMPLETE")
    print("============================================================")


asyncio.run(main())
