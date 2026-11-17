import io
import json
from pathlib import Path

import relate

from commoncause.matrix import matrix
from commoncause.replay import replay
from commoncause.topology import load_topology
from sim.bench import records

BENCH = Path(__file__).resolve().parents[1] / "topologies" / "cubesat-bench.yaml"
F1 = BENCH.parents[1] / "recordings" / "f1-fixture.jsonl"


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


def test_scoring_nine_bench_faults(tmp_path):
    recording = tmp_path / "bench-fixtures.jsonl"
    recording.write_text("\n".join(map(json.dumps, records())))
    scores = matrix(recording, BENCH)
    expected = [
        ["REG_B"], ["I2C-1"], ["I2C-3"], ["sun2"], ["RAIL_5V"],
        ["UART0"], ["drv.imu"], ["sun2"], ["REG_B", "I2C-3"],
    ]
    assert [row["ranked"] for row in scores] == expected
    assert sum(row["baseline"] == row["expected"][0] for row in scores) == 2
    rail_loss = scores[4]
    assert rail_loss["decision_ms"] == 1000
    assert rail_loss["latest_verdict_ms"] > rail_loss["decision_ms"]


def test_interleaved_replies_reduce_confidence():
    with relate.connect() as db:
        load_topology(db, BENCH)
        replay(db, io.StringIO("\n".join(map(json.dumps, records("F8")))))
        verdict, = snapshot(db)
        assert verdict["suspect"] == "sun2"
        assert verdict["confidence"] == "medium"
        assert db.execute("""
            MATCH (:Diagnosis)-[:MATCHES]->(fm:FailureMode)
            RETURN fm.id AS mode
        """).fetchone() == {"mode": "connector-intermittent"}


def test_first_commit_timestamp_survives_live_reranking():
    readings = list(records("F5"))
    run = readings[0]["run"]
    epoch = readings[0]["ts"]
    committed = []

    def commit_clock():
        committed.append(epoch + 2020)
        return committed[-1]

    with relate.connect() as db:
        load_topology(db, BENCH)
        replay(db, io.StringIO("\n".join(map(json.dumps, readings))), source="live", commit_clock=commit_clock)
        row = db.execute("""
            MATCH (dx:Diagnosis {run: $run})
            RETURN dx.first_commit_ts AS committed, dx.ts AS updated, dx.first_verdict_ts AS first
        """, {"run": run}).fetchone()

    assert committed == [epoch + 2020]
    assert row["committed"] == committed[0]
    assert row["updated"] > row["first"]
