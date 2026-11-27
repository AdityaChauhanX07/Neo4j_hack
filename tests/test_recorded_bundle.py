import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

import relate
import yaml

from commoncause.downlink import graph_json
from commoncause.matrix import matrix
from reference_rank import reference_rank

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "topologies" / "cubesat-bench.yaml"


def test_recorded_bundle_hashes_export_and_persisted_results_agree():
    manifest = json.loads((ROOT / "docs" / "virtual-matrix-manifest.json").read_text())
    for name, expected in manifest["files"].items():
        payload = (ROOT / name).read_bytes()
        assert len(payload) == expected["bytes"]
        assert sha256(payload).hexdigest() == expected["sha256"], name
    exported = json.loads((ROOT / "downlink" / "virtual-matrix.json").read_text())
    topology = yaml.safe_load(TOPOLOGY.read_text())
    with relate.connect(str(ROOT / "data" / "virtual-matrix.rl"), read_only=True) as db:
        assert graph_json(db) == exported
        run = db.execute("MATCH (r:Run) RETURN properties(r) AS props").fetchone()["props"]
        assert run["simulated"] is True and run["complete"] is True
        assert run["code_sha"] == manifest["code_sha"]
        assert run["detection_sha"] == manifest["detection_sha"]
        assert run["topology_sha"] == manifest["topology_sha"]
        events = db.execute("""
            MATCH (e:Event)-[:ON]->(ch:TelemetryChannel)
            RETURN e.run AS run, e.ts AS ts, e.status AS status, ch.id AS channel
        """).fetchall()
        episodes = db.execute("""
            MATCH (dx:Diagnosis)
            RETURN dx.id AS id, dx.run AS run, dx.window_from AS start,
                   dx.window_to AS stop, dx.state AS state
        """).fetchall()
        assert len(episodes) == 36 and all(row["state"] == "resolved" for row in episodes)
        for episode in episodes:
            remaining, expected = [], []
            for _ in range(3):
                ranking = reference_rank(topology, events, run=episode["run"],
                                         start=episode["start"], stop=episode["stop"], excluded=remaining)
                if not ranking:
                    break
                expected.append(ranking[0]["suspect"])
                if ranking[0]["score"] == 1:
                    break
                remaining.extend(ranking[0]["covered_devices"])
            actual = db.execute("""
                MATCH (:Diagnosis {id: $id})-[s:SUSPECTS]->(c)
                RETURN c.id AS id ORDER BY s.rank
            """, {"id": episode["id"]}).fetchall()
            assert [row["id"] for row in actual] == expected


def test_the_committed_raw_matrix_preserves_causes_after_gap_confirmation():
    scores = matrix(ROOT / "recordings" / "virtual-matrix.jsonl", TOPOLOGY)
    report = json.loads((ROOT / "docs" / "virtual-matrix-results.json").read_text())
    for current, recorded in zip(scores, report["injections"]):
        assert {key: current[key] for key in ("run", "fault", "expected", "ranked", "baseline")} == {
            key: recorded[key] for key in ("run", "fault", "expected", "ranked", "baseline")
        }
        if current["fault"] not in {"F5", "F6", "F7"}:
            assert current == recorded
        else:
            assert current["first_correct_ms"] >= recorded["first_correct_ms"]
    assert Counter(row["fault"] for row in scores) == {f"F{i}": 4 for i in range(1, 10)}
    assert all(row["ranked"] == row["expected"] and row["first_correct_ms"] is not None for row in scores)
    assert all(row["first_correct_ms"] > row["decision_ms"] for row in scores if row["fault"] == "F5")
