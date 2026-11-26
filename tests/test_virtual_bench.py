import io
import json
import sys
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

import pytest
import relate
import yaml

from commoncause import cli
from commoncause.benchmark import benchmark
from commoncause.board.drivers import I2C_DRIVERS
from commoncause.board.heartbeat import Heartbeats
from commoncause.board.i2c import I2CDevice
from commoncause.board.recorder import Recorder, ScriptedConsole
from commoncause.board import recorder as capture_module
from commoncause.board.settings import load_board
from commoncause.board.virtual import VirtualBench, VirtualBus, VirtualUART
from commoncause.replay import replay
from commoncause.topology import load_topology
from commoncause.view import diagnosis

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware" / "cubesat-pi4.yaml"
TOPOLOGY = ROOT / "topologies" / "cubesat-bench.yaml"


def test_virtual_registers_run_through_the_sensor_drivers():
    board = load_board(HARDWARE, TOPOLOGY)
    bench = VirtualBench(board, TOPOLOGY)
    observed = {}
    for device in board.devices.values():
        if device.chip == "heartbeat":
            continue
        port = I2CDevice(VirtualBus(bench, board.i2c[device.bus]), Lock(),
                         device.address, bench.transports.message)
        factory = I2C_DRIVERS[device.chip]
        driver = factory(port, device.shunt_ohms) if device.chip == "ina219" else factory(port)
        driver.initialize()
        observed[device.id] = driver.read()
    assert observed["imu"] == {"gyro": [1, 0, 0], "accel": [0, 0, 1]}
    assert observed["mag"]["field"] == [1, -2, 3]
    assert observed["epsmon"] == pytest.approx({"voltage": 3.3, "current": 11})
    assert observed["sun1"]["lux"] == observed["sun2"]["lux"] == 150
    assert observed["thermal"]["temperature"] == pytest.approx(25.08, abs=0.01)
    assert 990 < observed["payload"]["pressure"] < 1020
    assert bench.writes[1, 0x68, 0x6B] == b"\x01"
    assert bench.commands[3, 0x23] == 0x10


def test_virtual_faults_use_the_configured_adapters_and_addresses(tmp_path):
    hardware = yaml.safe_load(HARDWARE.read_text())
    hardware["buses"].update({"I2C-1": 6, "I2C-3": 8})
    hardware["devices"]["mag"]["address"] = 0x0C
    path = tmp_path / "hardware.yaml"
    path.write_text(yaml.safe_dump(hardware))
    board = load_board(path, TOPOLOGY)
    bench = VirtualBench(board, TOPOLOGY)
    bus = VirtualBus(bench, 6)
    assert bus.read_i2c_block_data(0x0C, 0x0D, 1) == [0xFF]
    bench.mark("F1", "inject", [])
    with pytest.raises(OSError):
        bus.read_i2c_block_data(0x0C, 0x0D, 1)
    assert bus.read_i2c_block_data(0x40, 0x02, 2) == list((40 << 3).to_bytes(2, "big"))
    bench.mark("F1", "clear", [])
    assert bus.read_i2c_block_data(0x0C, 0x0D, 1) == [0xFF]
    assert bus.read_i2c_block_data(0x40, 0x02, 2) == list((825 << 3).to_bytes(2, "big"))


def test_virtual_hmc_chip_id_and_axis_order(tmp_path):
    hardware = yaml.safe_load(HARDWARE.read_text())
    topology = yaml.safe_load(TOPOLOGY.read_text())
    hardware["devices"]["mag"].update(chip="hmc5883l", address=0x1E)
    next(part for part in topology["devices"] if part["id"] == "mag")["part"] = "HMC5883L"
    for name, config in [("hardware", hardware), ("topology", topology)]:
        (tmp_path / f"{name}.yaml").write_text(yaml.safe_dump(config))
    board = load_board(tmp_path / "hardware.yaml", tmp_path / "topology.yaml")
    bench = VirtualBench(board, tmp_path / "topology.yaml")
    port = I2CDevice(VirtualBus(bench, 1), Lock(), 0x1E)
    driver = I2C_DRIVERS["hmc5883l"](port)
    driver.initialize()
    assert driver.read()["field"] == [10, -20, 30]


def test_virtual_uart_splits_frames_and_loses_heartbeat_with_its_supply():
    now = [0.0]
    board = load_board(HARDWARE, TOPOLOGY)
    bench = VirtualBench(board, TOPOLOGY, clock=lambda: now[0])
    uart = VirtualUART(bench, board.devices["radio"], 0)
    decoder = Heartbeats()
    assert list(decoder.feed(uart.read(1))) == []
    assert list(decoder.feed(uart.read(uart.in_waiting))) == [0]
    bench.mark("F5", "inject", [])
    now[0] = 2
    assert uart.read(256) == b""
    assert bench.offline(board.devices["imu"])
    assert not bench.offline(board.devices["epsmon"])
    bench.mark("F5", "clear", [])
    now[0] = 3
    assert list(decoder.feed(uart.read(256))) == [3]


def test_rejected_virtual_marker_does_not_change_fault_state():
    now = [0.0]
    board = load_board(HARDWARE, TOPOLOGY)
    bench = VirtualBench(board, TOPOLOGY, clock=lambda: now[0])
    recorder = Recorder("virtual", on_marker=bench.mark, simulated=True)
    with pytest.raises(ValueError, match="I2C device"):
        recorder.mark("F8 inject radio")
    assert not bench.active and not recorder.active
    recorder.mark("F8 inject sun2")
    assert bench.offline(board.devices["sun2"])
    now[0] = 0.75
    assert not bench.offline(board.devices["sun2"])
    recorder.mark("F8 clear")
    assert not bench.active and not recorder.active


def test_intermittent_replies_do_not_alias_three_healthy_poll_boundaries():
    now = [0.0]
    board = load_board(HARDWARE, TOPOLOGY)
    bench = VirtualBench(board, TOPOLOGY, clock=lambda: now[0])
    bench.mark("F8", "inject", ["sun2"])
    replies = []
    for instant in (0.999, 1.501, 1.999):
        now[0] = instant
        replies.append(not bench.offline(board.devices["sun2"]))
    assert not all(replies)
    bench.mark("F8", "clear", [])
    assert not bench.offline(board.devices["sun2"])


def test_scenario_rejects_out_of_order_commands_and_missing_quit(tmp_path):
    path = tmp_path / "scenario.json"
    for steps in [
        [{"at": 2, "command": "F1 inject"}, {"at": 1, "command": "quit"}],
        [{"at": 0, "command": "F1 inject"}],
    ]:
        path.write_text(json.dumps(steps))
        with pytest.raises(ValueError):
            ScriptedConsole(path, io.StringIO())


def test_windows_console_keeps_polling_while_a_command_is_being_typed(monkeypatch):
    chars = list("F1 injex")
    monkeypatch.setattr(capture_module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(
        kbhit=lambda: bool(chars), getwch=lambda: chars.pop(0),
    ))
    console = capture_module.OperatorConsole(SimpleNamespace(isatty=lambda: True), io.StringIO())
    assert console.read() is None
    chars.extend("\bct\r")
    assert console.read() == "F1 inject"


def test_replay_preserves_simulation_provenance_and_rejects_mixed_metadata(tmp_path):
    from sim.bench import records

    rows = [dict(row, simulated=True) for row in records("F1") if "channel" in row]
    store = tmp_path / "virtual-store"
    with relate.connect(str(store)) as db:
        load_topology(db, TOPOLOGY)
        replay(db, io.StringIO("\n".join(map(json.dumps, rows))))
        verdict = diagnosis(db)
        assert verdict["simulated"] is True
        assert benchmark(db, store, samples=3)["simulated"] is True
    rows[-1].pop("simulated")
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        with pytest.raises(ValueError, match="metadata must be consistent"):
            replay(db, io.StringIO("\n".join(map(json.dumps, rows))))
        assert db.execute("MATCH (r:Run) RETURN r.simulated AS simulated, r.complete AS complete").fetchone() == {
            "simulated": True, "complete": False,
        }


def test_virtual_capture_needs_no_board_packages_and_stays_healthy(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "smbus2", None)
    monkeypatch.setitem(sys.modules, "serial", None)
    store = tmp_path / "store"
    recording = tmp_path / "healthy.jsonl"
    monkeypatch.setattr(sys, "argv", [
        "commoncause", "run", "--virtual-bench", "--db", str(store),
        "--recording", str(recording), "--duration", "1.5", "--run", "virtual-healthy",
    ])
    assert cli.main() == 0
    assert "Virtual bench: simulated" in capsys.readouterr().err
    rows = list(map(json.loads, recording.read_text().splitlines()))
    assert all(row["simulated"] is True and row["ok"] for row in rows)
    assert len({row["channel"] for row in rows}) == 11
    assert [row["seq"] for row in rows] == list(range(1, len(rows) + 1))
    with relate.connect(str(store), read_only=True) as db:
        assert diagnosis(db) is None
        assert db.execute("MATCH (r:Run) RETURN r.simulated AS simulated").fetchone() == {"simulated": True}


def test_full_virtual_session_records_scores_and_recovers(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "smbus2", None)
    monkeypatch.setitem(sys.modules, "serial", None)
    store = tmp_path / "store"
    recording = tmp_path / "virtual-session.jsonl"
    monkeypatch.setattr(sys, "argv", [
        "commoncause", "run", "--virtual-bench", "--db", str(store),
        "--scenario", str(ROOT / "sim" / "scenarios" / "f1-f9.json"),
        "--recording", str(recording), "--run", "virtual-matrix", "--duration", "65",
    ])
    assert cli.main() == 0
    messages = capsys.readouterr().err
    assert messages.count("Marker recorded:") == 18
    assert "Marker rejected" not in messages
    monkeypatch.setattr(sys, "argv", [
        "commoncause", "matrix", str(recording), "--bench-repeats", "1", "--min-top-one", "1", "--json",
    ])
    assert cli.main() == 0
    report = json.loads(capsys.readouterr().out)
    (tmp_path / "virtual-session-report.json").write_text(json.dumps(report, indent=2) + "\n")
    assert report["totals"]["all_causes"] == 9
    assert report["totals"]["recorded_first_correct_ms"]["samples"] == 9
    rail_loss = next(row for row in report["injections"] if row["fault"] == "F5")
    assert rail_loss["first_correct_ms"] > rail_loss["decision_ms"]
    with relate.connect(str(store), read_only=True) as db:
        states = db.execute("MATCH (dx:Diagnosis) RETURN dx.state AS state").fetchall()
        assert len(states) == 9 and all(row["state"] == "resolved" for row in states)
    replayed = tmp_path / "replayed"
    with relate.connect(str(replayed)) as db, recording.open() as feed:
        load_topology(db, TOPOLOGY)
        replay(db, feed)
        assert db.execute("MATCH (r:Run) RETURN r.simulated AS simulated").fetchone() == {"simulated": True}
