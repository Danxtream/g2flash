import re
import sys
import time
import serial

DEVICE = "COM5"

p = serial.Serial()
p.port = DEVICE
p.baudrate = 1_000_000
p.bytesize = serial.EIGHTBITS
p.parity = serial.PARITY_NONE
p.stopbits = serial.STOPBITS_ONE
p.timeout = 0.2
p.write_timeout = 1.0

# Open, then deliberately force the NORMAL boot selection/reset
# while the Windows CH340 handle is already open.
p.dtr = True
p.rts = True

print()
print("============================================================")
print("G2 CASE NORMAL-APPLICATION RETURN")
print("NO TEMPLE COMMAND / NO DEB0 / NO OTA / NO FLASH")
print("============================================================")

try:
    p.open()

    time.sleep(0.150)

    # Normal-flash boot selection.
    p.dtr = True

    # Assert reset.
    p.rts = True
    time.sleep(0.300)

    p.reset_input_buffer()

    # Release reset into normal case firmware.
    p.rts = False

    time.sleep(1.200)

    all_data = bytearray()

    for attempt in range(1, 4):

        p.reset_input_buffer()

        p.write(b"DEA0\n")
        p.flush()

        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            all_data.extend(p.read(4096))

        p.reset_input_buffer()

        p.write(b"DEA3\n")
        p.flush()

        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            all_data.extend(p.read(4096))

        versions = re.findall(
            rb"\bB200 ([0-9.]+)",
            all_data
        )

        presence = re.findall(
            rb"GLS_L:(\d+), GLS_R:(\d+)",
            all_data
        )

        if versions and presence:
            break

        time.sleep(0.300)

    print()
    print(all_data.decode("latin1", errors="replace"))
    print()

    if not versions:
        raise RuntimeError(
            "CASE_VERSION not returned"
        )

    version = versions[-1].decode()

    print("CASE_VERSION =", version)

    if version != "1.2.57":
        raise RuntimeError(
            "Unexpected case version: " + version
        )

    if presence:
        left, right = presence[-1]

        print("GLS_L =", left.decode())
        print("GLS_R =", right.decode())

    print()
    print("CASE_APPLICATION_RETURN = PASS")

except Exception as e:

    print()
    print("CASE_APPLICATION_RETURN = FAIL")
    print(type(e).__name__ + ":", e)
    sys.exit(1)

finally:
    if p.is_open:
        p.close()
