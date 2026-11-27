import io
import json
from collections import Counter
from pathlib import Path

import pytest
import relate

from commoncause.matrix import matrix
from commoncause.replay import replay
from commoncause.topology import load_topology
from sim.bench import records

TOPOLOGY = Path(__file__).resolve().parents[1] / "topologies" / "cubesat-bench.yaml"


def test_seed_reproduces_the_recording():
    assert list(records(seed=42)) == list(records(seed=42))
    assert list(records(seed=42)) != list(records(seed=7))


@pytest.mark.parametrize("seed", [7, 42, 2026])
def test_varied_faults_keep_their_causes_and_recover(seed, tmp_path):
    rows = list(records(seed=seed, repeats=4))
    recording = tmp_path / "varied.jsonl"
    recording.write_text("\n".join(map(json.dumps, rows)))

    scores = matrix(recording, TOPOLOGY)

    assert Counter(score["fault"] for score in scores) == {f"F{i}": 4 for i in range(1, 10)}
    for score in scores:
        assert score["ranked"][:1] == score["expected"][:1], score
        assert set(score["ranked"]) == set(score["expected"]), score
        assert score["first_correct_ms"] is not None, score
        if score["fault"] == "F5":
            assert score["first_correct_ms"] > score["decision_ms"], score

    # Injection labels are for scoring; replay must infer the causes without them.
    feed = io.StringIO("\n".join(json.dumps(row) for row in rows if "channel" in row))
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, feed)
        diagnoses = db.execute("""
            MATCH (dx:Diagnosis)-[s:SUSPECTS]->(c)
            RETURN dx.run AS run, dx.state AS state, c.id AS suspect
            ORDER BY dx.run, s.rank
        """).fetchall()
    for score in scores:
        verdict = [row for row in diagnoses if row["run"] == score["run"]]
        assert [row["suspect"] for row in verdict] == score["ranked"]
        assert all(row["state"] == "resolved" for row in verdict)


@pytest.mark.parametrize("seed", [7, 42, 2026])
def test_healthy_noise_and_jitter_do_not_open_an_episode(seed):
    feed = io.StringIO("\n".join(map(json.dumps, records("healthy", seed=seed, repeats=4))))
    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, feed)
        assert db.execute("MATCH (dx:Diagnosis) RETURN count(dx) AS count").fetchone() == {"count": 0}
