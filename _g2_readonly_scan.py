import asyncio
from bleak import BleakScanner

async def main():
    print("READ-ONLY BLE SCAN")
    print("NO CONNECTIONS / NO WRITES / NO FLASH")
    print()

    devices = await BleakScanner.discover(timeout=30.0)

    print("TOTAL DEVICES =", len(devices))
    print()

    matches = []

    for d in devices:
        name = getattr(d, "name", None) or ""
        address = getattr(d, "address", None) or ""
        rssi = getattr(d, "rssi", None)

        if "even" in name.lower() or "g2" in name.lower():
            matches.append((name, address, rssi))

    print("G2/EVEN CANDIDATES =", len(matches))
    print()

    if matches:
        for name, address, rssi in matches:
            print(
                "G2_FOUND NAME={!r} ADDR={} RSSI={}".format(
                    name,
                    address,
                    rssi
                )
            )
    else:
        print("NO G2/EVEN NAME FOUND")
        print()
        print("NAMED DEVICES SEEN:")

        for d in devices:
            name = getattr(d, "name", None) or ""
            address = getattr(d, "address", None) or ""
            if name:
                print(
                    "NAME={!r} ADDR={}".format(
                        name,
                        address
                    )
                )

asyncio.run(main())
