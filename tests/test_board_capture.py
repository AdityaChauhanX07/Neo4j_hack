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

    def sensor_feed(_args):
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
