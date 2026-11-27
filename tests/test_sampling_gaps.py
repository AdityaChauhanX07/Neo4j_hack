import io
import json
from pathlib import Path

import relate
import pytest
import yaml

from commoncause.diagnose import rank
from commoncause.replay import replay
from commoncause.topology import load_topology
from sim.bench import records

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "topologies" / "cubesat-bench.yaml"


def paused_capture(*, missing_driver=False):
    rows = list(records("healthy"))
    start = rows[0]["ts"]
    return [row for row in rows if not 1000 <= row["ts"] - start < 5000
            and not (missing_driver and row["channel"] in {"imu.gyro", "imu.accel"}
                     and row["ts"] >= start + 1000)]


def test_late_healthy_readings_preserve_gaps_without_component_diagnoses():
    rows = paused_capture()
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, io.StringIO("\n".join(map(json.dumps, rows))))
        assert db.execute("MATCH (d:Diagnosis) RETURN count(d) AS n").fetchone()["n"] == 0
        gaps = db.execute("""
            MATCH (e:Event) WHERE e.status IN ['STALE', 'HEARTBEAT_LOST']
            RETURN e.ts AS ts, e.observed_ts AS observed, e.diagnostic AS diagnostic
        """).fetchall()
        assert gaps and all(row["diagnostic"] is False and row["observed"] > row["ts"] for row in gaps)
        assert rank(db, rows[0]["run"], rows[0]["ts"], rows[-1]["ts"]) == ([], "low")
        assert db.execute("MATCH (r:Run) RETURN r.gap_events AS n").fetchone()["n"] == len(gaps)


def test_driver_still_missing_after_capture_resumes_is_confirmed_from_observation():
    rows = paused_capture(missing_driver=True)
    start = rows[0]["ts"]
    decisions = []

    def observe(db, run):
        if db.execute("MATCH (d:Diagnosis) RETURN count(d) AS n").fetchone()["n"]:
            decisions.append(run.last_ts)

    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, io.StringIO("\n".join(map(json.dumps, rows))), on_frame=observe)
        assert decisions[0] == start + 6000
        suspect = db.execute("MATCH (:Diagnosis)-[:SUSPECTS]->(p) RETURN p.id AS id").fetchone()
        assert suspect == {"id": "drv.imu"}
        assert rank(db, rows[0]["run"], start, start + 5500) == ([], "low")


def test_a_reading_at_the_confirmation_boundary_clears_the_pending_gap():
    rows = list(records("healthy"))
    start = rows[0]["ts"]
    rows = [row for row in rows if row["channel"] != "imu.gyro"
            or not 1000 <= row["ts"] - start < 3000]
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, map(json.dumps, rows))
        assert db.execute("MATCH (d:Diagnosis) RETURN count(d) AS n").fetchone()["n"] == 0
        gap, = db.execute("MATCH (e:Event {status: 'STALE'}) RETURN e.diagnostic AS diagnostic").fetchall()
        assert gap["diagnostic"] is False


def test_whole_stream_pause_restarts_confirmation_for_an_already_pending_gap():
    rows = list(records("healthy"))
    start = rows[0]["ts"]
    rows = [row for row in rows if not 2500 <= row["ts"] - start < 6000
            and (row["channel"] != "imu.gyro" or not 500 <= row["ts"] - start < 6000)]
    for row in rows:
        if row["channel"] == "imu.gyro" and row["ts"] == start + 6000:
            row["ts"] += 100
    rows.sort(key=lambda row: row["ts"])
    for seq, row in enumerate(rows, 1):
        row["seq"] = seq
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, map(json.dumps, rows))
        assert db.execute("MATCH (d:Diagnosis) RETURN count(d) AS n").fetchone()["n"] == 0


def test_a_transient_gap_does_not_add_a_suspect_to_an_existing_fault():
    rows = list(records("F4"))
    start = rows[0]["ts"]
    rows = [row for row in rows if row.get("channel") != "imu.gyro"
            or not 1000 <= row["ts"] - start < 2500]
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, map(json.dumps, rows))
        assert db.execute("""
            MATCH (d:Diagnosis)-[:SUSPECTS]->(p)
            RETURN p.id AS id, d.state AS state
        """).fetchall() == [{"id": "sun2", "state": "resolved"}]
        assert db.execute("""
            MATCH (:Diagnosis)-[:BASED_ON]->(e:Event {diagnostic: false})
            RETURN count(e) AS n
        """).fetchone()["n"] == 0
        ranked, _ = rank(db, rows[0]["run"], start, rows[-1]["ts"])
        assert [row["suspect"] for row in ranked] == ["sun2"]


def test_explicit_errors_after_a_pause_still_open_a_component_diagnosis():
    rows = paused_capture()
    start = rows[0]["ts"]
    for row in rows:
        if row["channel"] == "sun2.lux" and row["ts"] >= start + 5000:
            row.update(ok=False, value=None, error="EREMOTEIO")
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, map(json.dumps, rows))
        assert db.execute("""
            MATCH (d:Diagnosis)-[:SUSPECTS]->(p)
            RETURN p.id AS id, d.ts AS decided, d.window_from AS opened
        """).fetchall() == [{"id": "sun2", "decided": start + 6000, "opened": start + 5000}]


def test_confirmed_missing_telemetry_can_extend_an_existing_fault_window():
    rows = list(records("healthy"))
    start = rows[0]["ts"]
    rows = [row for row in rows if row["channel"] not in {"imu.gyro", "imu.accel"}
            or row["ts"] == start]
    for row in rows:
        if row["channel"] == "sun2.lux" and row["ts"] >= start + 2000:
            row.update(ok=False, value=None, error="EREMOTEIO")
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, map(json.dumps, rows))
        diagnoses = db.execute("""
            MATCH (d:Diagnosis)-[:SUSPECTS]->(p)
            RETURN d.window_from AS opened, p.id AS suspect
        """).fetchall()
        assert {row["suspect"] for row in diagnoses} == {"drv.imu", "sun2"}
        assert all(row["opened"] == start + 1500 for row in diagnoses)


@pytest.mark.parametrize("monitor,confirmed", [("REG_B", 3500), ("REG_A", 4000)])
def test_heartbeat_confirmation_uses_voltage_only_on_its_shared_power_path(tmp_path, monitor, confirmed):
    topology = yaml.safe_load(TOPOLOGY.read_text())
    power = next(device for device in topology["devices"] if device["id"] == "epsmon")
    next(channel for channel in power["channels"] if channel["id"] == "eps.regb.voltage")["monitors"] = monitor
    path = tmp_path / "wiring.yaml"
    path.write_text(yaml.safe_dump(topology))
    rows = list(records("F5"))
    start = rows[0]["ts"]
    with relate.connect() as db:
        load_topology(db, path)
        replay(db, map(json.dumps, rows))
        gap, = db.execute("""
            MATCH (e:Event {status: 'HEARTBEAT_LOST'})
            RETURN e.confirmed_ts AS confirmed
        """).fetchall()
        assert gap["confirmed"] == start + confirmed
