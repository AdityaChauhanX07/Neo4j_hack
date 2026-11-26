import gzip
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

import relate

from commoncause.check_capture import check_capture
from commoncause.replay import replay
from commoncause.topology import load_topology

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "topologies" / "cubesat-bench.yaml"


def report(name):
    return json.loads((ROOT / "docs" / name).read_text())


def test_runtime_profile_sources_and_recordings_match_the_manifest():
    manifest = report("runtime-profile-manifest.json")
    for name, expected in manifest["files"].items():
        payload = (ROOT / name).read_bytes()
        assert len(payload) == expected["bytes"], name
        assert sha256(payload).hexdigest() == expected["sha256"], name
        if "raw_sha256" in expected:
            assert sha256(gzip.decompress(payload)).hexdigest() == expected["raw_sha256"], name
    modes = report("final-mode-profile.json")
    recovery = report("final-recovery-profile.json")
    for measurements, source in [(modes, "profile_modes.py"), (recovery, "profile_recovery.py")]:
        assert measurements["code_sha"] == manifest["backend_code_sha"]
        assert measurements["runner_sha256"] == sha256((ROOT / "scripts" / source).read_bytes()).hexdigest()
    assert modes["poller_sha256"] == sha256((ROOT / "scripts" / "poll-live.mjs").read_bytes()).hexdigest()
    benchmark = report("final-rank-benchmark.json")
    assert benchmark["graph_sha256"] == sha256((ROOT / benchmark["graph"]).read_bytes()).hexdigest()


def test_repeat_captures_are_healthy_and_the_failed_pilot_remains_unhealthy():
    modes = report("final-mode-profile.json")
    assert Counter(run["mode"] for run in modes["runs"]) == {
        "baseline": 2, "live": 2, "recovery": 2, "combined": 2,
    }
    for run in modes["runs"]:
        with gzip.open(ROOT / run["recording"], "rt", encoding="utf-8") as feed:
            health = check_capture(feed, TOPOLOGY, min_seconds=59, min_rate=0.9)
        assert health["healthy"] and run["healthy"] and run["diagnoses"] == 0
        if "poller" in run:
            assert run["poller"]["failed"] == 0 and run["poller"]["polls"] == 60
    pilot = report("profile-pilot-gap.json")
    with gzip.open(ROOT / pilot["recording"], "rt", encoding="utf-8") as feed:
        health = check_capture(feed, TOPOLOGY, min_seconds=59, min_rate=0.9)
    assert health == pilot["capture_health"] and not health["healthy"]
    assert not pilot["healthy"] and pilot["diagnoses"] == 1
    assert pilot["included_in_mode_medians"] is False


def test_recovery_captures_preserve_the_reported_fault_and_resolution():
    runs = report("final-recovery-profile.json")["runs"]
    assert Counter(run["outcome"] for run in runs) == {"verified": 3, "not_recovered": 3}
    for run in runs:
        payload = gzip.decompress((ROOT / run["recording"]).read_bytes())
        assert sha256(payload).hexdigest() == run["recording_sha256"]
        with relate.connect() as db:
            load_topology(db, TOPOLOGY)
            replay(db, payload.decode().splitlines())
            diagnoses = db.execute("""
                MATCH (d:Diagnosis)-[s:SUSPECTS]->(c)
                RETURN d.state AS state, d.confidence AS confidence, c.id AS target
                ORDER BY s.rank
            """).fetchall()
        assert diagnoses == [{"state": run["diagnosis"], "confidence": run["confidence"], "target": run["target"]}]
