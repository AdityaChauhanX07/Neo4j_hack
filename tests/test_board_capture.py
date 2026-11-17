import errno
import json
import runpy
import sys
import time
from pathlib import Path
from struct import pack
from types import SimpleNamespace

import pytest
import relate
import yaml

from commoncause import cli
from commoncause.board.heartbeat import Heartbeats
from commoncause.board.recorder import Recorder
from commoncause.board.settings import load_board
from commoncause.view import diagnosis
from sim.bench import records

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware" / "cubesat-pi4.yaml"
TOPOLOGY = ROOT / "topologies" / "cubesat-bench.yaml"


def test_config_binds_every_channel():
    board = load_board(HARDWARE, TOPOLOGY)
    assert len(board.devices) == 8
    assert sum(len(sensor.outputs) for sensor in board.devices.values()) == 11
    assert board.i2c == {"I2C-1": 1, "I2C-3": 3}
    assert board.stall_driver == "drv.imu"


def test_config_rejects_i2c_address_collision(tmp_path):
    config = yaml.safe_load(HARDWARE.read_text())
    config["devices"]["mag"]["address"] = config["devices"]["imu"]["address"]
    path = tmp_path / "hardware.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="Duplicate address"):
        load_board(path, TOPOLOGY)


def test_pico_frame_and_serial_decoder_agree(monkeypatch):
    wire = []
    waits = []

    class Finished(Exception):
        pass

    def wait(interval):
        waits.append(interval)
        if len(waits) == 2:
            raise Finished

    def open_uart(index, *, baudrate, tx, rx):
        assert (index, baudrate, tx, rx) == (0, 115200, 0, 1)
        return SimpleNamespace(write=wire.append)

    monkeypatch.setitem(sys.modules, "machine", SimpleNamespace(Pin=int, UART=open_uart))
    monkeypatch.setattr(time, "sleep_ms", wait, raising=False)
    with pytest.raises(Finished):
        runpy.run_path(str(ROOT / "firmware" / "radio-standin" / "main.py"))
    assert waits == [1000, 1000]

    decoder = Heartbeats()
    assert list(decoder.feed(b"\xffnoise\n" + wire[0][:3])) == []
    assert list(decoder.feed(wire[0][3:] + wire[1])) == [0, 1]
    assert list(decoder.feed(b"CC1 4294967296\n" + b"x" * 80 + b"CC1 2\nCC1 3\r\n")) == [3]


def test_fault_markers_share_sequence_and_f7_suppresses_one_channel():
    recorder = Recorder("mark-test", "imu.gyro", "drv.imu")
    readings = [("imu.gyro", [0, 0, 0], None), ("imu.accel", [0, 0, 1], None)]
    inject = json.loads(recorder.mark("F7 inject"))
    active = list(map(json.loads, recorder.readings(readings)))
    clear = json.loads(recorder.mark("F7 clear"))
    recovered = list(map(json.loads, recorder.readings(readings)))

    assert inject["expected"] == ["drv.imu"]
    assert [row["channel"] for row in active] == ["imu.accel"]
    assert [row["channel"] for row in recovered] == ["imu.gyro", "imu.accel"]
    assert clear["action"] == "clear"
    complete = [inject, *active, clear, *recovered]
    assert [row["seq"] for row in complete] == list(range(1, 6))
    assert [row["ts"] for row in complete] == sorted(row["ts"] for row in complete)
    with pytest.raises(ValueError, match="F8 needs"):
        recorder.mark("F8 inject")


def test_record_cli_preserves_raw_bus_error_and_recovers(tmp_path, monkeypatch):
    opened = []

    class ImuBus:
        def __init__(self, bus):
            assert bus == 1
            self.initializations = 0
            self.samples = 0
            self.closed = False
            opened.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def write_i2c_block_data(self, address, register, values):
            assert address == 0x68
            if register == 0x6B:
                self.initializations += 1

        def read_i2c_block_data(self, address, register, size):
            assert address == 0x68
            if register == 0x75:
                return [0x68]
            assert (register, size) == (0x3B, 14)
            self.samples += 1
            if self.samples == 2:
                raise OSError(errno.EREMOTEIO, "I2C device did not answer")
            return list(pack(">7h", 0, 0, 8192, 0, 131, 0, 0))

    monkeypatch.setitem(sys.modules, "smbus2", SimpleNamespace(SMBus=ImuBus))
    monkeypatch.setitem(sys.modules, "serial", SimpleNamespace(Serial=None))
    recording = tmp_path / "imu.jsonl"
    monkeypatch.setattr(sys, "argv", [
        "commoncause", "record", "--device", "imu", "--duration", "1.6", "--run", "pi-test",
        "--out", str(recording), "--hardware", str(HARDWARE), "--topology", str(TOPOLOGY),
    ])

    assert cli.main() == 0
    rows = list(map(json.loads, recording.read_text().splitlines()))
    gyro = [row for row in rows if row["channel"] == "imu.gyro"]
    assert [row["ok"] for row in gyro[:3]] == [True, False, True]
    assert gyro[1]["value"] is None and gyro[1]["error"] == "EREMOTEIO"
    assert gyro[2]["value"] == [1, 0, 0]
    assert opened[0].initializations == 2 and opened[0].closed
    assert cli.main() == 1
    assert len(opened) == 1


def test_run_cli_saves_capture_and_persists_the_verdict(tmp_path, monkeypatch):
    stream = [json.dumps(row) + "\n" for row in records("F1")]

    def sensor_feed(_args, *, clock):
        yield from stream

    monkeypatch.setattr(cli, "board_feed", sensor_feed)
    store = tmp_path / "store"
    recording = tmp_path / "f1.jsonl"
    monkeypatch.setattr(sys, "argv", [
        "commoncause", "run", "--db", str(store), "--hardware", str(HARDWARE),
        "--topology", str(TOPOLOGY), "--recording", str(recording),
    ])

    assert cli.main() == 0
    assert recording.read_text() == "".join(stream)
    with relate.connect(str(store), read_only=True) as db:
        result = diagnosis(db)
    assert result["suspects"][0]["id"] == "REG_B"
    assert result["state"] == "resolved"


def test_two_buses_and_uart_record_a_complete_f1_episode(tmp_path, monkeypatch):
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
    powered_by_reg_b = {(1, 0x68), (1, 0x0D), (3, 0x23)}
    opened = set()
    started = None

    def undervoltage():
        return 0.8 <= time.monotonic() - started < 2.9

    class IlluminanceRead:
        def __init__(self, address, size):
            assert size == 2
            self.address = address

        def __bytes__(self):
            return pack(">H", 180)

    class Bus:
        def __init__(self, number):
            nonlocal started
            self.number = number
            if started is None:
                started = time.monotonic()

        def __enter__(self):
            opened.add(self.number)
            return self

        def __exit__(self, *args):
            opened.remove(self.number)

        def check_power(self, address):
            if undervoltage() and (self.number, address) in powered_by_reg_b:
                raise OSError(errno.EREMOTEIO, "REG_B disconnected")

        def read_i2c_block_data(self, address, register, size):
            self.check_power(address)
            if (address, register) == (0x40, 0x02):
                reading = pack(">H", (40 if undervoltage() else 825) << 3)
            else:
                reading = registers[self.number, address][register]
            assert len(reading) == size
            return list(reading)

        def write_i2c_block_data(self, address, register, values):
            self.check_power(address)

        def write_byte(self, address, command):
            self.check_power(address)

        def i2c_rdwr(self, message):
            self.check_power(message.address)

    class Uart:
        in_waiting = 0

        def __init__(self, port, **options):
            assert port == "/dev/serial0" and options["baudrate"] == 115200
            self.counter = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            time.sleep(0.10)
            self.counter += 1
            if self.counter % 5 == 1:
                return f"CC1 {self.counter}\n".encode()
            return b""

    monkeypatch.setitem(sys.modules, "smbus2", SimpleNamespace(
        SMBus=Bus, i2c_msg=SimpleNamespace(read=IlluminanceRead),
    ))
    monkeypatch.setitem(sys.modules, "serial", SimpleNamespace(Serial=Uart))
    store = tmp_path / "board"
    recording = tmp_path / "physical-shape.jsonl"
    monkeypatch.setattr(sys, "argv", [
        "commoncause", "run", "--db", str(store), "--hardware", str(HARDWARE),
        "--topology", str(TOPOLOGY), "--recording", str(recording), "--duration", "4.8",
    ])

    assert cli.main() == 0
    assert not opened
    rows = list(map(json.loads, recording.read_text().splitlines()))
    failed = {row["channel"] for row in rows if row["error"] == "EREMOTEIO"}
    assert failed == {"imu.gyro", "imu.accel", "mag.field", "sun1.lux"}
    assert len({row["channel"] for row in rows if row["ok"]}) == 11
    assert [row["seq"] for row in rows] == list(range(1, len(rows) + 1))
    assert [row["ts"] for row in rows] == sorted(row["ts"] for row in rows)

    with relate.connect(str(store), read_only=True) as db:
        result = diagnosis(db)
        timing = db.execute("""
            MATCH (dx:Diagnosis {id: $id})
            RETURN dx.first_commit_ts AS committed, dx.window_from AS started
        """, {"id": result["id"]}).fetchone()
    assert timing["committed"] - timing["started"] >= 1000
    assert timing["committed"] <= rows[-1]["ts"]
    assert result["state"] == "resolved"
    suspect = result["suspects"][0]
    assert (suspect["id"], suspect["covered"], suspect["contradicted"]) == ("REG_B", 3, 0)
    assert any(event["status"] == "UNDERVOLTAGE" for event in result["evidence"])
