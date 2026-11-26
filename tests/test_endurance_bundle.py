import gzip
import json
from hashlib import sha256
from pathlib import Path

from commoncause.check_capture import check_capture

ROOT = Path(__file__).resolve().parents[1]


def test_saved_healthy_captures_reproduce_hashes_and_channel_health():
    hour = json.loads((ROOT / "docs" / "endurance-results.json").read_text())
    ten = json.loads((ROOT / "docs" / "ten-minute-health.json").read_text())
    manifest = json.loads((ROOT / "docs" / "endurance-manifest.json").read_text())
    assert hour["passed"] is True and hour["diagnoses"] == 0
    assert hour["elapsed_seconds"] >= 3600
    for name, expected in manifest["files"].items():
        payload = (ROOT / name).read_bytes()
        assert len(payload) == expected["bytes"]
        assert sha256(payload).hexdigest() == expected["sha256"], name
    for filename, expected, seconds, digest in [
        ("virtual-healthy-hour.jsonl.gz", hour["capture_health"], 3599, hour["recording_sha256"]),
        ("virtual-healthy-ten-minute.jsonl.gz", {key: ten[key] for key in ("healthy", "runs")}, 600, ten["recording_sha256"]),
    ]:
        recording = ROOT / "recordings" / filename
        checksum = sha256()
        with gzip.open(recording, "rb") as feed:
            for block in iter(lambda: feed.read(65536), b""):
                checksum.update(block)
        assert checksum.hexdigest() == digest
        with gzip.open(recording, "rt", encoding="utf-8") as feed:
            actual = check_capture(feed, ROOT / "topologies" / "cubesat-bench.yaml", min_seconds=seconds, min_rate=0.9)
        assert actual == expected and actual["healthy"]
