import io
import json
from pathlib import Path

import relate

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
            or not 1000 <= row["ts"] - start < 3500]
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, map(json.dumps, rows))
        assert db.execute("MATCH (d:Diagnosis) RETURN count(d) AS n").fetchone()["n"] == 0
        gap, = db.execute("MATCH (e:Event {status: 'STALE'}) RETURN e.diagnostic AS diagnostic").fetchall()
        assert gap["diagnostic"] is False


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
