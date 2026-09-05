import re
import sys
import time
import serial
from serial.tools import list_ports

print()
print("============================================================")
print("G2 RETAIL CASE - READ ONLY DIAGNOSTIC")
print("NO RESET / NO OTA / NO FIRMWARE / NO ERASE")
print("============================================================")
print()

ports = list(list_ports.comports())

print("SERIAL PORTS:")
for p in ports:
    print(
        f"  {p.device}: "
        f"description={p.description!r} "
        f"vid={p.vid!r} pid={p.pid!r} "
        f"manufacturer={p.manufacturer!r}"
    )

# WCH CH340/CH341 family uses USB VID 0x1A86.
wch = [p for p in ports if p.vid == 0x1A86]

if len(wch) == 0:
    print()
    print("STOP: No WCH/CH340 serial port detected.")
    print("Make sure the CASE is connected to the PC with a DATA-capable USB cable.")
    print("Nothing was sent.")
    sys.exit(0)

if len(wch) > 1:
    print()
    print("STOP: More than one WCH/CH340 serial port is attached.")
    print("Disconnect unrelated CH340 devices and rerun.")
    print("Nothing was sent.")
    sys.exit(0)

dev = wch[0].device

print()
print("CASE SERIAL CANDIDATE =", dev)
print()
print("Opening retail case console at 1,000,000 baud...")

port = serial.Serial()
port.port = dev
port.baudrate = 1_000_000
port.bytesize = serial.EIGHTBITS
port.parity = serial.PARITY_NONE
port.stopbits = serial.STOPBITS_ONE
port.timeout = 0.2
port.write_timeout = 1.0
port.dtr = True
port.rts = True

captured = bytearray()

try:
    port.open()
    time.sleep(0.05)
    port.rts = False

    # Passive banner collection.
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        captured.extend(port.read(4096))

    # READ-ONLY case firmware-version query.
    port.reset_input_buffer()
    port.write(b"DEA0\n")
    port.flush()

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        captured.extend(port.read(4096))

    # READ-ONLY glasses-presence telemetry query.
    port.reset_input_buffer()
    port.write(b"DEA3\n")
    port.flush()

    deadline = time.monotonic() + 1.2
    while time.monotonic() < deadline:
        captured.extend(port.read(4096))

finally:
    if port.is_open:
        port.close()

raw = bytes(captured)

print()
print("============================================================")
print("RAW CASE RESPONSE")
print("============================================================")
print(raw.decode("latin1", errors="replace"))

versions = re.findall(rb"\bB200 ([0-9.]+)", raw)
presence = re.findall(rb"GLS_L:(\d+), GLS_R:(\d+)", raw)
ota = re.findall(rb"otaGls:(\d+)", raw)

print()
print("============================================================")
print("PARSED RESULT")
print("============================================================")

if versions:
    version = versions[-1].decode("ascii", errors="replace")
    print("CASE_VERSION =", version)

    if version == "1.2.57":
        print("CASE_VERSION_CHECK = PASS")
    else:
        print("CASE_VERSION_CHECK = STOP - EXPECTED 1.2.57")
else:
    print("CASE_VERSION = NOT FOUND")
    print("CASE_VERSION_CHECK = STOP")

if presence:
    l, r = presence[-1]
    print("GLS_L =", l)
    print("GLS_R =", r)

    if l == b"1" and r == b"1":
        print("CONTACT_STATE = BOTH TEMPLES PRESENT TO CASE")
    elif l == b"1" and r == b"0":
        print("CONTACT_STATE = LEFT PRESENT / RIGHT MISSING")
    elif l == b"0" and r == b"1":
        print("CONTACT_STATE = LEFT MISSING / RIGHT PRESENT")
    else:
        print("CONTACT_STATE = BOTH MISSING")
else:
    print("GLS_L / GLS_R = NOT FOUND")

if ota:
    print("otaGls =", ota[-1].decode("ascii"))

print()
print("============================================================")
print("READ-ONLY TEST COMPLETE")
print("NO DEB0 RESET WAS SENT")
print("NO FIRMWARE BYTES WERE SENT")
print("============================================================")
