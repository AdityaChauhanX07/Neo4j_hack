import io
import json
from pathlib import Path

import pytest
import relate
import yaml

from commoncause.diagnose import RANK
from commoncause.replay import replay
from commoncause.topology import load_topology
from reference_rank import reference_rank
from sim.bench import records
from sim.quad import records as quad_records

ROOT = Path(__file__).resolve().parents[1]
FAULTS = ["NO_RESPONSE", "OUT_OF_RANGE", "STUCK", "STALE", "HEARTBEAT_LOST"]


def compare(db, topology, events, run, start, stop):
    excluded = []
    for _ in range(3):
        expected = reference_rank(topology, events, run=run, start=start, stop=stop, excluded=excluded)
        actual = db.execute(RANK, {
            "run": run, "from": start, "to": stop,
            "device_faults": FAULTS, "exclude_devices": excluded,
        }).fetchall()
        assert len(actual) == len(expected)
        for measured, reference in zip(actual, expected):
            assert measured["score"] == pytest.approx(reference["score"])
            assert set(measured["covered_devices"]) == set(reference["covered_devices"])
            for key in ("suspect", "kind", "covered", "contradicted"):
                assert measured[key] == reference[key], (run, start, stop, measured, reference)
        if not expected or expected[0]["score"] == 1:
            break
        excluded.extend(expected[0]["covered_devices"])


@pytest.mark.parametrize("fault", [f"F{number}" for number in range(1, 10)])
def test_reference_agrees_for_every_bench_fault_and_reranking_window(fault):
    path = ROOT / "topologies" / "cubesat-bench.yaml"
    topology = yaml.safe_load(path.read_text())
    with relate.connect() as db:
        load_topology(db, path)
        replay(db, io.StringIO("\n".join(map(json.dumps, records(fault)))))
        events = db.execute("""
            MATCH (e:Event)-[:ON]->(ch:TelemetryChannel)
            RETURN e.run AS run, e.ts AS ts, e.status AS status, ch.id AS channel
        """).fetchall()
        episode = db.execute("""
            MATCH (dx:Diagnosis)
            RETURN dx.run AS run, dx.window_from AS start, dx.window_to AS stop
        """).fetchone()
        # Include the initial decision, before F5's missing heartbeat is known.
        for stop in sorted({episode["start"] + 1000, episode["stop"]}):
            compare(db, topology, events, episode["run"], episode["start"], stop)


def test_reference_agrees_on_the_second_topology():
    path = ROOT / "topologies" / "quadcopter.yaml"
    topology = yaml.safe_load(path.read_text())
    with relate.connect() as db:
        load_topology(db, path)
        replay(db, io.StringIO("\n".join(map(json.dumps, quad_records()))))
        events = db.execute("""
            MATCH (e:Event)-[:ON]->(ch:TelemetryChannel)
            RETURN e.run AS run, e.ts AS ts, e.status AS status, ch.id AS channel
        """).fetchall()
        for episode in db.execute("""
            MATCH (dx:Diagnosis)
            RETURN dx.run AS run, dx.window_from AS start, dx.window_to AS stop
        """).fetchall():
            compare(db, topology, events, episode["run"], episode["start"], episode["stop"])


def test_reference_distinguishes_unknown_healthy_and_failed_devices_at_window_boundaries():
    path = ROOT / "topologies" / "cubesat-bench.yaml"
    topology = yaml.safe_load(path.read_text())
    rows = [
        ("scope", "imu.gyro", 1000, "NO_RESPONSE"),
        ("scope", "mag.field", 1000, "NO_RESPONSE"),
        ("scope", "sun1.lux", 2000, "NO_RESPONSE"),
        ("scope", "eps.regb.voltage", 1000, "UNDERVOLTAGE"),
        ("scope", "thermal.temp", 999, "NO_RESPONSE"),
        ("scope", "thermal.temp", 1000, "OK"),
        ("scope", "radio.heartbeat", 2001, "HEARTBEAT_LOST"),
        ("other", "sun2.lux", 1500, "OK"),
    ]
    events = [dict(zip(("run", "channel", "ts", "status"), row)) for row in rows]
    with relate.connect() as db:
        load_topology(db, path)
        db.execute("""
            UNWIND $events AS row
            MATCH (ch:TelemetryChannel {id: row.channel})
            CREATE (:Event {run: row.run, ts: row.ts, status: row.status})-[:ON]->(ch)
        """, {"events": events})
        compare(db, topology, events, "scope", 1000, 2000)
        compare(db, topology, events, "other", 1000, 2000)
    ranked = reference_rank(topology, events, run="scope", start=1000, stop=2000)
    regulator = next(row for row in ranked if row["suspect"] == "REG_B")
    rail = next(row for row in ranked if row["suspect"] == "RAIL_5V")
    assert regulator["covered"] == 3
    assert regulator["score"] == rail["score"] == 1
    assert ranked[0]["suspect"] == "REG_B"
    assert next(row for row in ranked if row["suspect"] == "I2C-1")["contradicted"] == 2
