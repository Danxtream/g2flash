import re
import sys
import time
import serial

DEVICE = "COM5"
EXPECTED_CASE_VERSION = "1.2.57"

ACK = 0x79
SYNC = 0x7F


def drain(p, seconds):
    end = time.monotonic() + seconds
    out = bytearray()

    while time.monotonic() < end:
        chunk = p.read(4096)
        if chunk:
            out.extend(chunk)

    return bytes(out)


def app_framing(p):
    p.baudrate = 1_000_000
    p.bytesize = serial.EIGHTBITS
    p.parity = serial.PARITY_NONE
    p.stopbits = serial.STOPBITS_ONE
    p.timeout = 0.2
    p.write_timeout = 1.0


def rom_framing(p):
    p.baudrate = 115_200
    p.bytesize = serial.EIGHTBITS
    p.parity = serial.PARITY_EVEN
    p.stopbits = serial.STOPBITS_ONE
    p.timeout = 3.0
    p.write_timeout = 3.0


def query_normal_case(p):
    app_framing(p)

    p.reset_input_buffer()
    p.write(b"DEA0\n")
    p.flush()
    raw = bytearray(drain(p, 1.0))

    p.reset_input_buffer()
    p.write(b"DEA3\n")
    p.flush()
    raw.extend(drain(p, 1.2))

    raw = bytes(raw)

    version = re.findall(rb"\bB200 ([0-9.]+)", raw)
    presence = re.findall(
        rb"GLS_L:(\d+), GLS_R:(\d+)",
        raw
    )

    return raw, version, presence


def require_ack(p, label):
    b = p.read(1)

    if not b:
        raise RuntimeError(
            f"{label}: timeout waiting for ACK"
        )

    print(
        f"{label}_BYTE = 0x{b[0]:02X}"
    )

    if b[0] != ACK:
        raise RuntimeError(
            f"{label}: expected 0x79, got 0x{b[0]:02X}"
        )


def rom_identity(p):
    # STM32 GET command -- read-only.
    p.write(bytes((0x00, 0xFF)))
    p.flush()
    require_ack(p, "GET_ACK")

    n_raw = p.read(1)
    if not n_raw:
        raise RuntimeError("GET response length timeout")

    n = n_raw[0]
    response = p.read(n + 1)

    if len(response) != n + 1:
        raise RuntimeError(
            f"GET response truncated: {len(response)}/{n+1}"
        )

    require_ack(p, "GET_FINAL_ACK")

    protocol = response[0]
    commands = response[1:]

    print(
        f"ROM_PROTOCOL = 0x{protocol:02X}"
    )
    print(
        "ROM_COMMANDS =",
        " ".join(f"{x:02X}" for x in commands)
    )

    # STM32 GET_ID -- read-only.
    p.write(bytes((0x02, 0xFD)))
    p.flush()
    require_ack(p, "GET_ID_ACK")

    n_raw = p.read(1)
    if not n_raw:
        raise RuntimeError("GET_ID response length timeout")

    n = n_raw[0]
    raw_id = p.read(n + 1)

    if len(raw_id) != n + 1:
        raise RuntimeError(
            f"GET_ID truncated: {len(raw_id)}/{n+1}"
        )

    require_ack(p, "GET_ID_FINAL_ACK")

    product = int.from_bytes(raw_id, "big")

    print(
        f"ROM_PRODUCT_ID = 0x{product:04X}"
    )

    if protocol != 0x31:
        raise RuntimeError(
            f"unexpected ROM protocol 0x{protocol:02X}"
        )

    if product != 0x0467:
        raise RuntimeError(
            f"unexpected STM32 product 0x{product:04X}"
        )


def restore_case_app(p):
    print()
    print("RESTORING NORMAL CASE APPLICATION")

    # Configure host for normal case firmware BEFORE resetting.
    app_framing(p)

    # BOOT selection back to normal application.
    p.dtr = True
    time.sleep(0.250)

    # Assert reset.
    p.rts = True
    time.sleep(0.250)

    p.reset_input_buffer()

    # Release reset.
    p.rts = False

    time.sleep(1.0)

    raw, versions, presence = query_normal_case(p)

    print()
    print("CASE RESTORE RESPONSE:")
    print(
        raw.decode(
            "latin1",
            errors="replace"
        )
    )

    if not versions:
        raise RuntimeError(
            "normal B200 version response did not return"
        )

    version = versions[-1].decode(
        "ascii",
        errors="replace"
    )

    print("RESTORED_CASE_VERSION =", version)

    if version != EXPECTED_CASE_VERSION:
        raise RuntimeError(
            f"expected case {EXPECTED_CASE_VERSION}, "
            f"got {version}"
        )

    if presence:
        left, right = presence[-1]

        print(
            "RESTORED_GLS_L =",
            left.decode()
        )
        print(
            "RESTORED_GLS_R =",
            right.decode()
        )

    print("APP_RESTORE = PASS")


print()
print("============================================================")
print("G2 WINDOWS CH340 ROM-ENTRY TEST")
print("============================================================")
print("NO TEMPLE OTA")
print("NO TEMPLE FIRMWARE")
print("NO FLASH ERASE")
print("NO CASE FLASH WRITE")
print("NO RIGHT COMMAND")
print()
print("Purpose:")
print("  Avoid Windows open-time DTR/RTS glitch")
print("  Enter CASE STM32 ROM using one open COM handle")
print("  Read ROM identity")
print("  Return CASE to normal 1.2.57")
print("============================================================")
print()

p = serial.Serial()
p.port = DEVICE
p.baudrate = 1_000_000
p.bytesize = serial.EIGHTBITS
p.parity = serial.PARITY_NONE
p.stopbits = serial.STOPBITS_ONE
p.timeout = 0.2
p.write_timeout = 1.0

# Start in the known normal case configuration.
p.dtr = True
p.rts = True

rom_ok = False

try:
    p.open()

    # Known-good normal case reset sequence.
    time.sleep(0.150)
    p.rts = False
    time.sleep(0.750)

    print("STEP 1: verify normal case before ROM transition")

    raw, versions, presence = query_normal_case(p)

    if not versions:
        raise RuntimeError(
            "STOP: case 1.2.57 not reachable before test"
        )

    version = versions[-1].decode(
        "ascii",
        errors="replace"
    )

    print("CASE_VERSION =", version)

    if version != EXPECTED_CASE_VERSION:
        raise RuntimeError(
            f"STOP: unexpected case version {version}"
        )

    if not presence:
        raise RuntimeError(
            "STOP: GLS presence telemetry missing"
        )

    left, right = presence[-1]

    print("GLS_L =", left.decode())
    print("GLS_R =", right.decode())

    if right != b"1":
        raise RuntimeError(
            "STOP: RIGHT not reported present by case"
        )

    print("NORMAL_CASE_GATE = PASS")

    # ---------------------------------------------------------
    # Critical change from upstream recovery helper:
    #
    # Do NOT close/re-open COM5 with unusual DTR/RTS states.
    # Transition to BOOT0 + RESET while this working Windows
    # CH340 handle remains open.
    # ---------------------------------------------------------

    print()
    print("STEP 2: enter STM32 ROM WITHOUT reopening COM5")

    p.reset_input_buffer()
    p.reset_output_buffer()

    # Source recovery mapping:
    # DTR low = system memory / ROM boot selection.
    p.dtr = False
    time.sleep(0.250)

    # RTS asserted = reset.
    p.rts = True
    time.sleep(0.250)

    # Release reset while BOOT selection remains active.
    p.rts = False
    time.sleep(0.600)

    # Change only UART framing after the reset transition.
    rom_framing(p)

    p.reset_input_buffer()
    p.reset_output_buffer()

    time.sleep(0.150)

    print("Sending STM32 SYNC 0x7F...")

    p.write(bytes((SYNC,)))
    p.flush()

    sync = p.read(1)

    if not sync:
        raise RuntimeError(
            "ROM_SYNC: timeout; expected 0x79"
        )

    print(
        f"ROM_SYNC_BYTE = 0x{sync[0]:02X}"
    )

    if sync[0] != ACK:
        raise RuntimeError(
            f"ROM_SYNC: expected 0x79, got 0x{sync[0]:02X}"
        )

    print("ROM_SYNC = PASS")

    print()
    print("STEP 3: read immutable STM32 ROM identity")

    rom_identity(p)

    print()
    print("ROM_IDENTITY = PASS")
    rom_ok = True

except Exception as e:
    print()
    print("============================================================")
    print("TEST ERROR")
    print("============================================================")
    print(
        type(e).__name__ + ": " + str(e)
    )

finally:
    if p.is_open:
        try:
            restore_case_app(p)
        except Exception as restore_error:
            print()
            print("============================================================")
            print("CASE RESTORE VERIFICATION ERROR")
            print("============================================================")
            print(
                type(restore_error).__name__
                + ": "
                + str(restore_error)
            )
            print()
            print("STOP: do not run another case command.")
            p.close()
            sys.exit(2)

        p.close()


print()
print("============================================================")
print("FINAL RESULT")
print("============================================================")

if rom_ok:
    print("WINDOWS_ROM_ENTRY = PASS")
    print("CASE_RETURNED_TO_1.2.57 = PASS")
    print()
    print("NEXT PATH:")
    print("  Use this same no-reopen ROM transition")
    print("  with the reviewed SRAM bridge")
    print("  then issue ONE RIGHT read-version request.")
    sys.exit(0)

print("WINDOWS_ROM_ENTRY = FAIL")
print("CASE_RETURNED_TO_1.2.57 = PASS")
print()
print("No RIGHT operation was attempted.")
sys.exit(1)
