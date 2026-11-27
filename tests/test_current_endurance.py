import gzip
import json
from hashlib import sha256
from pathlib import Path

import relate

from commoncause.check_capture import check_capture
from commoncause.replay import replay
from commoncause.topology import load_topology

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "topologies" / "cubesat-bench.yaml"


def test_current_endurance_bundle_preserves_full_input_and_prefix_health():
    manifest = json.loads((ROOT / "docs" / "final-endurance-manifest.json").read_text())
    hour = json.loads((ROOT / "docs" / "final-endurance-results.json").read_text())
    ten = json.loads((ROOT / "docs" / "final-ten-minute-health.json").read_text())
    assert hour["elapsed_seconds"] >= 3600
    assert hour["code_sha"] == manifest["code_sha"] == ten["code_sha"]
    assert hour["runner_sha256"] == manifest["files"]["scripts/soak.py"]["sha256"]
    for name, expected in manifest["files"].items():
        payload = (ROOT / name).read_bytes()
        assert len(payload) == expected["bytes"], name
        assert sha256(payload).hexdigest() == expected["sha256"], name
    for name, expected, digest, seconds in [
        ("hour-current.jsonl.gz", hour["capture_health"], hour["recording_sha256"], 3599),
        ("ten-minute-prefix.jsonl.gz", {key: ten[key] for key in ("healthy", "runs")}, ten["recording_sha256"], 600),
    ]:
        payload = gzip.decompress((ROOT / "recordings" / "runtime-profile" / name).read_bytes())
        assert sha256(payload).hexdigest() == digest
        rows = payload.decode().splitlines()
        assert all(json.loads(row).get("type") != "fault" for row in rows)
        assert check_capture(rows, TOPOLOGY, min_seconds=seconds, min_rate=0.9) == expected
    assert ten["healthy"] is True
    assert hour["passed"] == (hour["capture_health"]["healthy"] and hour["diagnoses"] == 0)


def test_saved_hour_retains_gaps_without_repeating_historical_diagnoses():
    report = json.loads((ROOT / "docs" / "final-endurance-results.json").read_text())
    evidence = json.loads((ROOT / "docs" / "final-endurance-diagnoses.json").read_text())
    updated = json.loads((ROOT / "docs" / "sampling-gap-replay-results.json").read_text())["hour"]
    assert updated["raw_sha256"] == report["recording_sha256"]
    assert updated["capture_code_sha"] == report["code_sha"]
    with gzip.open(ROOT / "recordings" / "runtime-profile" / "hour-current.jsonl.gz", "rt", encoding="utf-8") as feed:
        with relate.connect() as db:
            load_topology(db, TOPOLOGY)
            replay(db, feed)
            count = db.execute("MATCH (d:Diagnosis) RETURN count(d) AS n").fetchone()["n"]
            gaps = db.execute("""
                MATCH (e:Event) WHERE e.status IN ['STALE', 'HEARTBEAT_LOST']
                RETURN e.diagnostic AS diagnostic, e.observed_ts AS observed, e.ts AS ts
            """).fetchall()
    assert report["diagnoses"] == 3 and len({row["id"] for row in evidence["rows"]}) == 3
    assert count == updated["replay_diagnoses"] == 0
    assert updated["capture_healthy"] is False
    assert len(gaps) == updated["gap_events"] == 19
    assert gaps and all(row["diagnostic"] is False and row["observed"] > row["ts"] for row in gaps)
