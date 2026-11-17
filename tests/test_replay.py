import io
import json
from pathlib import Path

import pytest
import relate

from commoncause.replay import replay
from commoncause.topology import load_topology

BENCH = Path(__file__).resolve().parents[1] / "topologies" / "cubesat-bench.yaml"
F1 = BENCH.parents[1] / "recordings" / "f1-fixture.jsonl"
REG_B = {"imu.gyro", "imu.accel", "mag.field", "sun1.lux"}
BUS_1 = {"imu.gyro", "imu.accel", "mag.field", "eps.regb.voltage", "eps.regb.current", "thermal.temp"}
BUS_3 = {"sun1.lux", "sun2.lux", "payload.temp", "payload.pressure"}


def snapshot(db):
    return db.execute("""
        MATCH (dx:Diagnosis)-[s:SUSPECTS]->(c)
        RETURN dx.id AS diagnosis, dx.state AS state, dx.confidence AS confidence,
               c.id AS suspect, s.covered AS covered
        ORDER BY dx.id, s.rank
    """).fetchall()


def test_replay_links_verdict_to_evidence_and_recovery(tmp_path):
    store = tmp_path / "store"
    with relate.connect(str(store)) as db:
        load_topology(db, BENCH)
        with F1.open() as feed:
            replay(db, feed)

    with relate.connect(str(store), read_only=True) as db:
        assert snapshot(db) == [{
            "diagnosis": "dx:f1-fixture:1", "state": "resolved",
            "confidence": "high", "suspect": "REG_B", "covered": 3,
        }]
        assert db.execute("""
            MATCH (:Diagnosis)-[:BASED_ON]->(e:Event {status: 'UNDERVOLTAGE'})
                  -[:ON]->(ch:TelemetryChannel)
            RETURN ch.id AS channel
        """).fetchone() == {"channel": "eps.regb.voltage"}
        assert db.execute("""
            MATCH (:Diagnosis)-[:RESOLVED_AT]->(e:Event)
            RETURN e.status AS status
        """).fetchone() == {"status": "OK"}


def test_fault_markers_do_not_affect_verdict():
    with relate.connect() as db:
        load_topology(db, BENCH)
        feed = io.StringIO("".join(
            line for line in F1.read_text().splitlines(keepends=True)
            if json.loads(line).get("type") != "fault"
        ))
        replay(db, feed)
        assert [row["suspect"] for row in snapshot(db)] == ["REG_B"]


@pytest.mark.parametrize(("failed", "silent", "undervoltage", "expected"), [
    (BUS_1, set(), False, ["I2C-1"]),
    (BUS_3, set(), False, ["I2C-3"]),
    ({"sun2.lux"}, set(), False, ["sun2"]),
    (REG_B, {"radio.heartbeat"}, True, ["RAIL_5V"]),
    (set(), {"radio.heartbeat"}, False, ["UART0"]),
    (set(), {"imu.gyro"}, False, ["drv.imu"]),
    (REG_B | BUS_3, set(), True, ["REG_B", "I2C-3"]),
])
def test_fixture_faults(failed, silent, undervoltage, expected):
    first_frame = {
        row["channel"]: row for row in map(json.loads, F1.read_text().splitlines())
        if row["ts"] == 1794873600000
    }
    rows = []
    for ts in range(0, 8001, 500):
        for channel, baseline in first_frame.items():
            if channel == "radio.heartbeat" and ts % 1000:
                continue
            reading = {**baseline, "ts": ts, "seq": len(rows)}
            if 1000 <= ts < 6000:
                if channel in silent:
                    continue
                if channel in failed:
                    reading.update(ok=False, value=None, error="EREMOTEIO")
                if undervoltage and channel == "eps.regb.voltage":
                    reading["value"] = 0.16
            rows.append(json.dumps(reading))

    with relate.connect() as db:
        load_topology(db, BENCH)
        replay(db, io.StringIO("\n".join(rows)))
        assert [row["suspect"] for row in snapshot(db)] == expected


def test_interleaved_replies_reduce_confidence():
    rows = []
    for line in F1.read_text().splitlines():
        row = json.loads(line)
        if row.get("type") == "fault":
            continue
        offset = row["ts"] - 1794873600000
        channel = row["channel"]
        if channel in REG_B:
            row.update(ok=True, error=None, value=0)
        if channel == "eps.regb.voltage":
            row["value"] = 3.28
        if channel == "sun2.lux" and offset in {1000, 2000}:
            row.update(ok=False, error="EREMOTEIO", value=None)
        rows.append(json.dumps(row))

    with relate.connect() as db:
        load_topology(db, BENCH)
        replay(db, io.StringIO("\n".join(rows)))
        verdict, = snapshot(db)
        assert verdict["suspect"] == "sun2"
        assert verdict["confidence"] == "medium"
        assert db.execute("""
            MATCH (:Diagnosis)-[:MATCHES]->(fm:FailureMode)
            RETURN fm.id AS mode
        """).fetchone() == {"mode": "connector-intermittent"}
