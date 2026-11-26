import io
import json
import sys
from pathlib import Path

import pytest
import relate

from commoncause import cli
from commoncause.board.settings import load_board
from commoncause.board.virtual import VirtualBench
from commoncause.recovery import VirtualRecovery
from commoncause.replay import replay
from commoncause.topology import load_topology
from sim.bench import records

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "topologies/cubesat-bench.yaml"
HARDWARE = ROOT / "hardware/cubesat-pi4.yaml"


@pytest.mark.parametrize("fault,target,persistent", [
    ("F2", "I2C-1", False), ("F3", "I2C-3", False), ("F2", "I2C-1", True),
])
def test_live_recovery_uses_observed_health_and_retains_failed_attempts(tmp_path, monkeypatch, capsys,
                                                                     fault, target, persistent):
    scenario = tmp_path / "scenario.json"
    # Leave room for detection and the full verification timeout on a busy host.
    scenario.write_text(json.dumps([
        {"at": 0.5, "command": f"{fault} inject"}, {"at": 7.5, "command": "quit"},
    ]))
    store, recording = tmp_path / "store", tmp_path / "capture.jsonl"
    args = ["commoncause", "run", "--virtual-bench", "--auto-recover", "--scenario", str(scenario),
            "--db", str(store), "--recording", str(recording), "--run", "recovery-check"]
    if persistent:
        args.append("--persistent-bus-fault")
    monkeypatch.setattr(sys, "argv", args)
    assert cli.main() == 0
    expected = "not_recovered" if persistent else "verified"
    assert expected in capsys.readouterr().err
    with relate.connect(str(store), read_only=True) as db:
        attempt, = db.execute("""
            MATCH (dx:Diagnosis)-[:ATTEMPTED]->(a:RecoveryAttempt)-[:TARGETS]->(b:Bus)
            RETURN a.id AS id, b.id AS target, a.state AS state, a.simulated AS simulated,
                   a.ts AS ts, a.finished AS finished, dx.state AS diagnosis
        """).fetchall()
        assert attempt["target"] == target and attempt["simulated"] is True
        assert attempt["state"] == expected and attempt["finished"] > attempt["ts"]
        if persistent:
            assert attempt["finished"] - attempt["ts"] >= 3000
        assert attempt["diagnosis"] == ("open" if persistent else "resolved")
        evidence = db.execute("""
            MATCH (a:RecoveryAttempt)-[:VERIFIED_BY]->(e:Event)
            RETURN e.ts AS ts, e.status AS status
        """).fetchall()
        assert len(evidence) == (0 if persistent else 1)
        assert all(row["status"] == "OK" and row["ts"] > attempt["ts"] for row in evidence)
        assert db.execute("MATCH (a:RecoveryAttempt) RETURN count(a) AS n").fetchone()["n"] == 1
    with relate.connect() as db, recording.open() as feed:
        load_topology(db, TOPOLOGY)
        replay(db, feed)
        assert db.execute("MATCH (dx:Diagnosis) RETURN dx.state AS state").fetchone()["state"] == attempt["diagnosis"]


@pytest.mark.parametrize("fault", ["F1", "F8", "F9"])
def test_recovery_refuses_power_faults_intermittency_and_multiple_causes(fault):
    bench = VirtualBench(load_board(HARDWARE, TOPOLOGY), TOPOLOGY)
    recovery = VirtualRecovery(bench, output=io.StringIO())
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        rows = [dict(row, simulated=True) for row in records(fault)]
        replay(db, io.StringIO("\n".join(map(json.dumps, rows))), on_frame=recovery.observe)
        assert not db.execute("MATCH (a:RecoveryAttempt) RETURN a.id AS id").fetchall()
    assert not bench.restored_buses


def test_capture_end_without_verification_is_not_recorded_as_success():
    bench = VirtualBench(load_board(HARDWARE, TOPOLOGY), TOPOLOGY)
    recovery = VirtualRecovery(bench, output=io.StringIO())
    rows = [dict(row, simulated=True) for row in records("F2") if "channel" in row]
    cutoff = rows[0]["ts"] + 2500
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, io.StringIO("\n".join(json.dumps(row) for row in rows if row["ts"] <= cutoff)),
               on_frame=recovery.observe)
        assert recovery.pending
        recovery.finish(db, cutoff)
        assert db.execute("MATCH (a:RecoveryAttempt) RETURN a.state AS state").fetchone() == {"state": "unverified"}
        assert not db.execute("MATCH (:RecoveryAttempt)-[:VERIFIED_BY]->(e) RETURN e").fetchall()


def test_bus_reinitialization_cannot_restore_power_or_a_persistent_fault():
    board = load_board(HARDWARE, TOPOLOGY)
    bench = VirtualBench(board, TOPOLOGY)
    bench.mark("F2", "inject", [])
    bench.clear_bus("I2C-1")
    assert not bench.offline(board.devices["imu"])
    bench.mark("F2", "clear", [])
    bench.mark("F2", "inject", [])
    assert bench.offline(board.devices["imu"])
    bench.mark("F1", "inject", [])
    bench.clear_bus("I2C-1")
    assert bench.offline(board.devices["imu"])
    persistent = VirtualBench(board, TOPOLOGY, recoverable_bus_faults=False)
    persistent.mark("F2", "inject", [])
    persistent.clear_bus("I2C-1")
    assert persistent.offline(board.devices["imu"])


def test_auto_recovery_rejects_a_physical_capture_before_opening_a_store(tmp_path, monkeypatch, capsys):
    store = tmp_path / "store"
    monkeypatch.setattr(sys, "argv", [
        "commoncause", "run", "--hardware", str(HARDWARE), "--auto-recover", "--db", str(store),
    ])
    assert cli.main() == 1
    assert "requires --virtual-bench" in capsys.readouterr().err
    assert not store.exists()
