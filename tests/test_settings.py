import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
import relate
import yaml

from commoncause.settings import DETECTION, DETECTION_SHA, DETECTION_TEXT, parse_detection

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("name", "value"), [
    ("stuck_samples", 0), ("recovery_samples", True),
    ("settle_ms", -1), ("heartbeat_timeout_ms", 1.5),
    ("undervoltage_ratio", float("nan")), ("undervoltage_ratio", 1.1),
])
def test_detection_config_rejects_unusable_thresholds(name, value):
    rules = yaml.safe_load(DETECTION_TEXT)
    rules[name] = value
    with pytest.raises(ValueError):
        parse_detection(yaml.safe_dump(rules))


def test_default_detection_config_is_packaged_and_hashed():
    assert DETECTION.stuck_samples == 10
    assert DETECTION.heartbeat_timeout_ms == 3000
    assert DETECTION_SHA == sha256(DETECTION_TEXT.encode()).hexdigest()


def test_a_new_process_uses_the_selected_config_and_records_its_hash(tmp_path):
    rules = yaml.safe_load(DETECTION_TEXT)
    rules["settle_ms"] = 500
    config = tmp_path / "detection.yaml"
    config.write_text(yaml.safe_dump(rules))
    store = tmp_path / "store"
    completed = subprocess.run([
        sys.executable, "-c", "from commoncause.cli import main; raise SystemExit(main())",
        "replay", str(ROOT / "recordings" / "f1-fixture.jsonl"),
        "--topology", str(ROOT / "topologies" / "cubesat-bench.yaml"), "--db", str(store),
    ], env={**os.environ, "COMMONCAUSE_DETECTION_CONFIG": str(config)},
        cwd=ROOT, text=True, capture_output=True, timeout=20)
    assert completed.returncode == 0, completed.stderr
    with relate.connect(str(store), read_only=True) as db:
        run = db.execute("MATCH (r:Run) RETURN r.detection_sha AS sha").fetchone()
        verdict = db.execute("MATCH (dx:Diagnosis) RETURN coalesce(dx.first_verdict_ts, dx.ts) - dx.window_from AS elapsed").fetchone()
    assert run["sha"] == sha256(config.read_text().encode()).hexdigest()
    assert verdict["elapsed"] == 500
