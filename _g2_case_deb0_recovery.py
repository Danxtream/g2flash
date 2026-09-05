import re
import sys
import time
import serial
from serial.tools import list_ports

print()
print("============================================================")
print("G2 CASE DEB0 TEMPLE RESET")
print("NO OTA / NO FIRMWARE / NO ERASE")
print("THIS WILL REBOOT BOTH TEMPLES")
print("============================================================")
print()

ports = list(list_ports.comports())
wch = [p for p in ports if p.vid == 0x1A86]

if len(wch) != 1:
    print("STOP: Expected exactly one CH340/WCH case serial port.")
    print("Found:", len(wch))
    for p in wch:
        print(" ", p.device, p.description)
    sys.exit(0)

dev = wch[0].device
print("CASE PORT =", dev)


def open_case():
    p = serial.Serial()
    p.port = dev
    p.baudrate = 1_000_000
    p.bytesize = serial.EIGHTBITS
    p.parity = serial.PARITY_NONE
    p.stopbits = serial.STOPBITS_ONE
    p.timeout = 0.2
    p.write_timeout = 1.0
    p.dtr = True
    p.rts = True
    p.open()
    time.sleep(0.05)
    p.rts = False
    return p


def drain(p, seconds):
    end = time.monotonic() + seconds
    data = bytearray()
    while time.monotonic() < end:
        data.extend(p.read(4096))
    return bytes(data)


print()
print("Sending traced stock DEB0 bilateral temple reset...")

p = open_case()

try:
    # Clear any old console output first.
    drain(p, 2.5)
    p.reset_input_buffer()

    cmd = b"DEB0\n"

    if p.write(cmd) != len(cmd):
        raise RuntimeError("DEB0 write was truncated")

    p.flush()

    reset_raw = drain(p, 2.5)

finally:
    p.close()


print()
print("============================================================")
print("RESET RESPONSE")
print("============================================================")
print(reset_raw.decode("latin1", errors="replace"))

confirmed = bool(
    re.search(
        rb"reset gls L & R, reason: cmd",
        reset_raw,
        re.IGNORECASE
    )
)

print()
print("RESET_CONFIRMED =", confirmed)

if not confirmed:
    print()
    print("============================================================")
    print("STOP CONDITION")
    print("============================================================")
    print("The case did not confirm DEB0.")
    print("Do not send anything else.")
    sys.exit(0)


print()
print("DEB0 confirmed.")
print("Allowing the temple links to restart...")

# Same recovery interval used by the reviewed case recovery code.
time.sleep(6.5)


last_raw = b""
report = None

for attempt in range(1, 4):

    print()
    print(f"POST-RESET CASE CHECK {attempt}/3")

    p = None

    try:
        p = open_case()

        captured = bytearray(drain(p, 2.5))

        p.reset_input_buffer()
        p.write(b"DEA0\n")
        p.flush()
        captured.extend(drain(p, 0.9))

        p.reset_input_buffer()
        p.write(b"DEA3\n")
        p.flush()
        captured.extend(drain(p, 1.2))

        last_raw = bytes(captured)

    finally:
        if p is not None and p.is_open:
            p.close()

    versions = re.findall(
        rb"\bB200 ([0-9.]+)",
        last_raw
    )

    presence = re.findall(
        rb"GLS_L:(\d+), GLS_R:(\d+)",
        last_raw
    )

    if versions and presence:
        report = (
            versions[-1].decode("ascii", errors="replace"),
            presence[-1][0].decode(),
            presence[-1][1].decode(),
            attempt
        )
        break

    if attempt < 3:
        time.sleep(0.5)


print()
print("============================================================")
print("POST-RESET RAW CASE RESPONSE")
print("============================================================")
print(last_raw.decode("latin1", errors="replace"))

print()
print("============================================================")
print("POST-RESET RESULT")
print("============================================================")

if report is None:
    print("CASE_VERSION = NOT RESOLVED")
    print("GLS_L / GLS_R = NOT RESOLVED")
    print()
    print("STOP: Do not perform any firmware operation.")
    sys.exit(0)

version, left, right, attempt = report

print("CASE_VERSION =", version)
print("GLS_L =", left)
print("GLS_R =", right)
print("POST_RESET_ATTEMPT =", attempt)

right_fail = bool(
    re.search(
        rb"(Fail to get GLS_R status|No reply from GLS_R)",
        last_raw,
        re.IGNORECASE
    )
)

print("RIGHT_NO_REPLY_WARNING =", right_fail)

print()

if version != "1.2.57":
    print("STOP: Unexpected case firmware.")
elif left == "1" and right == "1" and not right_fail:
    print("RESULT = STRONG RECOVERY SIGNAL")
    print("Both temples present and no explicit RIGHT no-reply warning.")
elif left == "1" and right == "1" and right_fail:
    print("RESULT = RIGHT STILL PHYSICALLY PRESENT BUT NOT REPLYING")
    print("Do not flash anything.")
elif right == "0":
    print("RESULT = RIGHT NOT PRESENT TO CASE AFTER RESET")
    print("Do not flash anything.")
else:
    print("RESULT = INDETERMINATE")
    print("Do not flash anything.")

print()
print("============================================================")
print("DEB0 TEST COMPLETE")
print("NO FIRMWARE BYTES WERE SENT")
print("============================================================")
