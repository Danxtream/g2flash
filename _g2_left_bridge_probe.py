import asyncio
import time
from bleak import BleakScanner, BleakClient

LEFT = "C4:60:45:13:B3:36"

WRITE_UUID  = "00002760-08c2-11e1-9073-0e8ac72e5401"
NOTIFY_UUID = "00002760-08c2-11e1-9073-0e8ac72e5402"

SID_APP_LAUNCH = 0x01
SID_EVENHUB    = 0xE0
FLAG_REQUEST   = 0x20

notes = asyncio.Queue()
transport_seq = 0


def crc16(data):
    c = 0xFFFF
    for b in data:
        c ^= b << 8
        for _ in range(8):
            if c & 0x8000:
                c = ((c << 1) ^ 0x1021) & 0xFFFF
            else:
                c = (c << 1) & 0xFFFF
    return bytes((c & 0xFF, (c >> 8) & 0xFF))


def varint(v):
    out = bytearray()
    v = int(v)
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def key(field, wire):
    return varint((field << 3) | wire)


def fv(field, value):
    return key(field, 0) + varint(value)


def fb(field, value):
    value = bytes(value)
    return key(field, 2) + varint(len(value)) + value


def fm(field, value):
    return fb(field, value)


def fs(field, value):
    return fb(field, value.encode("utf-8"))


def read_varint(buf, pos):
    value = 0
    shift = 0

    while pos < len(buf):
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift

        if not (b & 0x80):
            return value, pos

        shift += 7

    raise ValueError("truncated varint")


def protobuf_varint_field(buf, wanted):
    pos = 0

    try:
        while pos < len(buf):
            k, pos = read_varint(buf, pos)
            field = k >> 3
            wire = k & 7

            if wire == 0:
                value, pos = read_varint(buf, pos)
                if field == wanted:
                    return value

            elif wire == 2:
                ln, pos = read_varint(buf, pos)

                if field == wanted:
                    return None

                pos += ln

            elif wire == 1:
                pos += 8

            elif wire == 5:
                pos += 4

            else:
                return None

    except Exception:
        return None

    return None


def build_prelude():
    deepest = fv(1, 0) + fv(2, 0)
    a = fm(2, deepest)
    b = fm(2, a)
    c = fm(3, b)

    return (
        fv(1, 2) +
        fv(2, 156) +
        fm(4, c)
    )


def text_object():
    return (
        fv(1, 0) +
        fv(2, 0) +
        fv(3, 576) +
        fv(4, 288) +
        fv(9, 1) +
        fs(10, "dashboard") +
        fv(11, 1) +
        fs(12, " ")
    )


def image_object():
    return (
        fv(1, 0) +
        fv(2, 0) +
        fv(3, 576) +
        fv(4, 288) +
        fv(5, 10) +
        fs(6, "img00")
    )


def wrap_evenhub(cmd, magic, field, inner):
    return (
        fv(1, cmd) +
        fv(2, magic) +
        fm(field, inner)
    )


def build_layout(magic):
    inner = (
        fv(1, 2) +
        fm(3, text_object()) +
        fm(4, image_object()) +
        fv(5, 10000)
    )

    return wrap_evenhub(0, magic, 3, inner)


def build_image_payload(magic, payload):
    inner = (
        fv(1, 10) +
        fs(2, "img00") +
        fv(3, 10) +
        fv(4, len(payload)) +
        fv(5, 0) +
        fv(6, 0) +
        fv(7, len(payload)) +
        fb(8, payload)
    )

    return wrap_evenhub(3, magic, 5, inner)


def frames(sid, pb, flag=FLAG_REQUEST):
    global transport_seq

    transport_seq = (transport_seq + 1) & 0xFF
    seq = transport_seq

    body = pb + crc16(pb)
    chunk = 232
    total = max(1, (len(body) + chunk - 1) // chunk)

    result = []

    for i in range(total):
        part = body[i * chunk:(i + 1) * chunk]

        result.append(
            bytes([
                0xAA,
                0x21,
                seq,
                len(part),
                total,
                i + 1,
                sid,
                flag
            ]) + part
        )

    return result


def parse_reply(data):
    data = bytes(data)

    if (
        len(data) < 10 or
        data[0] != 0xAA or
        data[1] != 0x12
    ):
        return None

    ln = data[3]
    sid = data[6]

    pb_len = max(0, ln - 2)
    pb = data[8:8 + pb_len]

    return sid, pb


def notify(sender, data):
    raw = bytes(data)

    try:
        notes.put_nowait(raw)
    except Exception:
        pass


async def drain():
    while not notes.empty():
        try:
            notes.get_nowait()
        except Exception:
            break


async def write_message(client, sid, pb):
    for packet in frames(sid, pb):
        await client.write_gatt_char(
            WRITE_UUID,
            packet,
            response=False
        )

        await asyncio.sleep(0.025)


async def wait_ack(sid, magic, label, timeout=4.0):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()

        try:
            raw = await asyncio.wait_for(
                notes.get(),
                timeout=max(0.05, remaining)
            )
        except asyncio.TimeoutError:
            break

        parsed = parse_reply(raw)

        print(
            f"RX {label}: {raw.hex().upper()}"
        )

        if not parsed:
            continue

        rsid, pb = parsed

        if rsid != sid:
            continue

        rx_magic = protobuf_varint_field(pb, 2)

        if rx_magic is None or rx_magic == magic:
            return True

    return False


async def stage(client, label, sid, magic, pb):
    await drain()

    t0 = time.monotonic()

    print()
    print(f"SEND {label}")
    print(f"  SID   = 0x{sid:02X}")
    print(f"  MAGIC = {magic}")

    await write_message(client, sid, pb)

    ok = await wait_ack(
        sid,
        magic,
        label
    )

    ms = (time.monotonic() - t0) * 1000.0

    print(
        f"{label}_ACK = "
        f"{'OK' if ok else 'TIMEOUT'} "
        f"elapsed={ms:.1f}ms"
    )

    return ok


async def main():
    print()
    print("============================================================")
    print("G2 LEFT-ONLY INTER-LENS BRIDGE PROBE")
    print("============================================================")
    print("TARGET LEFT =", LEFT)
    print()
    print("IMPORTANT:")
    print("  NO OTA SERVICE")
    print("  NO FIRMWARE DATA CHARACTERISTIC")
    print("  NO FLASH / ERASE / FILE_CHECK")
    print("  NORMAL EVENHUB DISPLAY TRAFFIC ONLY")
    print()

    found = await BleakScanner.discover(
        timeout=20.0,
        return_adv=True
    )

    target = None

    for addr, pair in found.items():
        if addr.upper() == LEFT:
            target = pair[0]
            break

    if target is None:
        print("STOP: LEFT was not advertising.")
        return

    print(
        f"FOUND LEFT: "
        f"{target.address} "
        f"{target.name!r}"
    )

    async with BleakClient(target) as client:
        print(
            "CONNECTED LEFT =",
            client.is_connected
        )

        await client.start_notify(
            NOTIFY_UUID,
            notify
        )

        await asyncio.sleep(1.0)
        await drain()

        # ---------------------------------------------------------
        # 1. Try app-launch handshake THROUGH LEFT.
        # If this cannot ACK, do not continue.
        # ---------------------------------------------------------
        if not await stage(
            client,
            "PRELUDE",
            SID_APP_LAUNCH,
            156,
            build_prelude()
        ):
            print()
            print("============================================================")
            print("STOP CONDITION")
            print("============================================================")
            print("LEFT did not ACK the app-launch handshake.")
            print("NO LAYOUT OR ORIENTATION COMMAND WAS SENT.")
            print("Do not rerun. Paste this output.")
            return

        # ---------------------------------------------------------
        # 2. Create the same RX16 image carrier Faceclaw uses.
        # ---------------------------------------------------------
        if not await stage(
            client,
            "LAYOUT",
            SID_EVENHUB,
            41,
            build_layout(41)
        ):
            print()
            print("============================================================")
            print("STOP CONDITION")
            print("============================================================")
            print("Prelude ACKed but LEFT did not ACK layout creation.")
            print("NO ORIENTATION COMMAND WAS SENT.")
            print("Do not rerun. Paste this output.")
            return

        print()
        print("============================================================")
        print("LOOK THROUGH BOTH LENSES NOW")
        print("============================================================")
        print("Sending ONE existing RX16/RX17 orientation probe:")
        print("payload = 0B 07  ([11,7])")
        print()

        # Existing CFW mode-11 asymmetric orientation probe.
        ok = await stage(
            client,
            "ORIENTATION",
            SID_EVENHUB,
            42,
            build_image_payload(
                42,
                bytes([11, 7])
            )
        )

        print()
        print("============================================================")
        print("RESULT")
        print("============================================================")
        print(
            "ORIENTATION_ACK =",
            "OK" if ok else "TIMEOUT"
        )
        print()
        print("Tell me exactly:")
        print("  LEFT DISPLAY  = changed / unchanged")
        print("  RIGHT DISPLAY = changed / unchanged")
        print()
        print("Disconnecting without any firmware operation.")

        await asyncio.sleep(5.0)

        try:
            await client.stop_notify(
                NOTIFY_UUID
            )
        except Exception:
            pass


asyncio.run(main())
