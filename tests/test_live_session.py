"""A live F1 to F5 bench session driven through the operator terminal.

The sensors are simulated, but the session uses the same path as the bench:
`commoncause run --hardware --interactive`, typed markers on a real
pseudo-terminal, the live store, and `commoncause matrix` on the recording.
"""
import errno
import os
import sys
import threading
import time
from struct import pack
from types import SimpleNamespace

import pytest
import relate

from commoncause import cli
from commoncause.view import diagnosis

pty = pytest.importorskip("pty")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARDWARE = os.path.join(ROOT, "hardware", "cubesat-pi4.yaml")
TOPOLOGY = os.path.join(ROOT, "topologies", "cubesat-bench.yaml")

# Which (bus, address) pairs stop answering, and whether REG_B sags, per fault.
REG_B_DEVICES = {(1, 0x68), (1, 0x0D), (3, 0x23)}
BUS_1 = {(1, 0x68), (1, 0x0D), (1, 0x40), (1, 0x76)}
BUS_3 = {(3, 0x23), (3, 0x5C), (3, 0x77)}
SILENT = {"F1": REG_B_DEVICES, "F2": BUS_1, "F3": BUS_3, "F4": {(3, 0x5C)}, "F5": REG_B_DEVICES}
SAG = {"F1", "F5"}

# Seconds to hold each fault, then to wait for the episode to resolve.
# F5 also silences the 1 Hz heartbeat, which is declared lost after 3 seconds.
SESSION = [("F1", 2.0, 2.5), ("F2", 2.0, 2.5), ("F3", 2.0, 2.5), ("F4", 2.0, 2.5), ("F5", 4.0, 1.0)]


def no_answer():
    # EREMOTEIO is what Linux returns for a missing I2C reply.
    return OSError(getattr(errno, "EREMOTEIO", errno.EIO), "I2C device did not answer")


def simulated_bench(active):
    calibration = pack("<HhhH8h", 27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000)
    adc = (415148 << 4).to_bytes(3, "big") + (519888 << 4).to_bytes(3, "big")
    bme = {0xD0: b"\x60", 0xF3: b"\x00", 0x88: calibration, 0xF7: adc}
    registers = {
        (1, 0x68): {0x75: b"\x68", 0x3B: pack(">7h", 0, 0, 8192, 0, 131, 0, 0)},
        (1, 0x0D): {0x0D: b"\xff", 0x06: b"\x01", 0x00: pack("<3h", 120, -240, 360)},
        (1, 0x40): {0x01: b"\x00\x6e"},
        (1, 0x76): bme,
        (3, 0x77): bme,
    }

    class IlluminanceRead:
        def __init__(self, address, size):
            self.address = address

        def __bytes__(self):
            return pack(">H", 180)

    class Bus:
        def __init__(self, number):
            self.number = number

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def check(self, address):
            if any((self.number, address) in SILENT[fault] for fault in active):
                raise no_answer()

        def read_i2c_block_data(self, address, register, size):
            self.check(address)
            if (address, register) == (0x40, 0x02):
                return list(pack(">H", (40 if active & SAG else 825) << 3))
            return list(registers[self.number, address][register])

        def write_i2c_block_data(self, address, register, values):
            self.check(address)

        def write_byte(self, address, command):
            self.check(address)

        def i2c_rdwr(self, message):
            self.check(message.address)

    class Uart:
        in_waiting = 0

        def __init__(self, port, **options):
            self.counter = 0
            self.next_frame = time.monotonic()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            time.sleep(0.05)
            if "F5" in active or time.monotonic() < self.next_frame:
                return b""
            self.next_frame += 1.0
            self.counter += 1
            return f"CC1 {self.counter}\n".encode()

    smbus = SimpleNamespace(SMBus=Bus, i2c_msg=SimpleNamespace(read=IlluminanceRead))
    return smbus, SimpleNamespace(Serial=Uart)


def operate(terminal, active, done):
    """Type each marker, then change the simulated wiring, as the operator would."""
    def type_line(text):
        os.write(terminal, f"{text}\n".encode())

    time.sleep(2.0)
    for fault, hold, settle in SESSION:
        # As in hardware/bench-run.md: enter the marker, then open the switch.
        # A diagnosis that opens before its marker is not scored.
        type_line(f"{fault} inject")
        time.sleep(0.3)
        active.add(fault)
        time.sleep(hold)
        active.discard(fault)
        type_line(f"{fault} clear")
        time.sleep(settle)
    type_line("quit")
    done.set()


@pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX terminal")
def test_live_f1_to_f5_session_with_typed_markers(tmp_path, monkeypatch, capsys):
    active = set()
    smbus, serial = simulated_bench(active)
    monkeypatch.setitem(sys.modules, "smbus2", smbus)
    monkeypatch.setitem(sys.modules, "serial", serial)

    terminal, operator_side = pty.openpty()
    stdin = os.fdopen(operator_side, "r")
    monkeypatch.setattr(sys, "stdin", stdin)
    store = tmp_path / "board"
    recording = tmp_path / "bench-f1-f5.jsonl"
    monkeypatch.setattr(sys, "argv", [
        "commoncause", "run", "--db", str(store), "--hardware", HARDWARE, "--topology", TOPOLOGY,
        "--recording", str(recording), "--interactive", "--duration", "60",
    ])

    done = threading.Event()
    operator = threading.Thread(target=operate, args=(terminal, active, done), daemon=True)
    operator.start()
    try:
        assert cli.main() == 0
    finally:
        operator.join(timeout=5)
        stdin.close()
        os.close(terminal)
    assert done.is_set()
    messages = capsys.readouterr().err
    assert messages.count("Marker recorded:") == 10
    assert "Marker rejected" not in messages

    monkeypatch.setattr(sys, "argv", [
        "commoncause", "matrix", str(recording), "--topology", TOPOLOGY,
        "--expect-count", "5", "--min-top-one", "1",
    ])
    assert cli.main() == 0
    scored = capsys.readouterr().out
    for fault, expected in [("F1", "REG_B"), ("F2", "I2C-1"), ("F3", "I2C-3"), ("F4", "sun2"), ("F5", "RAIL_5V")]:
        line = next(row for row in scored.splitlines() if f" {fault} " in row)
        assert f"ranked {expected}" in line, line
    assert "Top-1 5/5" in scored
    assert "First correct verdicts 5/5" in scored

    with relate.connect(str(store), read_only=True) as db:
        latest = diagnosis(db)
    assert latest["suspects"][0]["id"] == "RAIL_5V"
