import io
import json
from pathlib import Path

import relate
import pytest

from commoncause.replay import replay
from commoncause.topology import load_topology
from commoncause.view import diagnosis

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "topologies" / "cubesat-bench.yaml"


def quiet_recording():
    fixture = list(map(json.loads, (ROOT / "recordings" / "f1-fixture.jsonl").read_text().splitlines()))
    epoch = fixture[0]["ts"]
    nominal = {row["channel"]: row["value"] for row in fixture if row["ts"] == epoch}
    rows = []
    for age in range(0, 9001, 500):
        for channel, value in nominal.items():
            if channel == "radio.heartbeat":
                if age % 1000:
                    continue
                value = age // 1000
            rows.append({
                "run": "held-out", "seq": len(rows) + 1, "ts": epoch + age,
                "channel": channel, "value": value, "ok": True, "simulated": True,
            })
    return epoch, rows


def verdict_history(rows):
    history = []

    def observe(db, run):
        verdict = diagnosis(db)
        if verdict:
            history.append((run.last_ts, verdict))

    with relate.connect() as db:
        load_topology(db, TOPOLOGY)
        replay(db, io.StringIO("\n".join(map(json.dumps, rows))), on_frame=observe)
    return history


def test_delayed_correlated_failures_replace_the_initial_device_suspect():
    epoch, rows = quiet_recording()
    for row in rows:
        age = row["ts"] - epoch
        channel = row["channel"]
        if (channel in {"imu.gyro", "imu.accel"} and 1000 <= age < 6000) or (
            channel in {"mag.field", "sun1.lux"} and 3000 <= age < 6000
        ):
            row.update(ok=False, value=None, error="EREMOTEIO")
        if channel == "eps.regb.voltage" and 3000 <= age < 6000:
            row["value"] = 0.16
    history = verdict_history(rows)
    assert history[0][1]["suspects"][0]["id"] == "imu"
    correct = next(at for at, verdict in history if verdict["suspects"][0]["id"] == "REG_B")
    assert correct >= epoch + 3000
    assert history[-1][1]["state"] == "resolved"


@pytest.mark.parametrize("seen_before_fault", [False, True])
def test_a_new_healthy_device_resolves_an_ambiguous_power_fault(seen_before_fault):
    epoch, rows = quiet_recording()
    rows = [row for row in rows if row["channel"] != "radio.heartbeat"
            or row["ts"] >= epoch + 3000 or (seen_before_fault and row["ts"] == epoch)]
    for row in rows:
        if 1000 <= row["ts"] - epoch < 6000:
            if row["channel"] in {"imu.gyro", "imu.accel", "mag.field", "sun1.lux"}:
                row.update(ok=False, value=None, error="EREMOTEIO")
            elif row["channel"] == "eps.regb.voltage":
                row["value"] = 0.16
    history = verdict_history(rows)
    first = history[0][1]
    assert first["suspects"][0]["id"] == "REG_B"
    assert first["confidence"] == "medium"
    informed = next(verdict for at, verdict in history if at == epoch + 3000)
    assert informed["confidence"] == "high"
    assert informed["suspects"][0]["id"] == "REG_B"
    assert history[-1][1]["state"] == "resolved"


def test_missing_driver_samples_remain_distinct_from_bus_errors():
    epoch, rows = quiet_recording()
    rows = [row for row in rows if row["channel"] != "imu.gyro" or not 1000 <= row["ts"] - epoch < 6000]
    history = verdict_history(rows)
    first = history[0][1]
    assert first["suspects"][0]["id"] == "drv.imu"
    assert first["confidence"] == "medium"
    assert {event["status"] for event in first["evidence"]} == {"STALE"}
    assert all(event["error"] is None for event in first["evidence"])
    assert history[-1][1]["state"] == "resolved"
