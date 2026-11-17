import io
import json
import sys
from pathlib import Path

from commoncause import cli
from commoncause.check_capture import check_capture
from sim.bench import FIXTURE

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "topologies" / "cubesat-bench.yaml"


def healthy_readings():
    fixture = list(map(json.loads, FIXTURE.read_text().splitlines()))
    first = fixture[0]["ts"]
    nominal = [row for row in fixture if row["ts"] == first and "channel" in row]
    seq = 0
    for ts in range(0, 5001, 500):
        for row in nominal:
            if row["channel"] == "radio.heartbeat" and ts % 1000:
                continue
            seq += 1
            yield {**row, "run": "health-check", "seq": seq, "ts": ts}


def test_health_check_reports_all_channels_at_the_expected_cadence():
    stream = io.StringIO("\n".join(map(json.dumps, healthy_readings())))
    result = check_capture(stream, BENCH, min_seconds=5)
    assert result["healthy"]
    run, = result["runs"]
    channels = {ch["id"]: ch for ch in run["channels"]}
    assert len(channels) == 11
    assert channels["imu.gyro"]["observed_hz"] == 2
    assert channels["radio.heartbeat"]["observed_hz"] == 1
    assert channels["radio.heartbeat"]["max_gap_ms"] == 1000


def test_health_check_cli_fails_with_missing_and_faulty_readings(tmp_path, monkeypatch, capsys):
    captured = tmp_path / "capture.jsonl"
    rows = []
    for row in healthy_readings():
        if row["channel"] == "radio.heartbeat":
            continue
        if row["channel"] == "imu.gyro" and row["ts"] == 500:
            row.update(ok=False, value=None, error="EREMOTEIO")
        rows.append(json.dumps(row))
    captured.write_text("\n".join(rows))
    monkeypatch.setattr(sys, "argv", [
        "commoncause", "check-capture", str(captured), "--topology", str(BENCH),
        "--min-seconds", "6", "--json",
    ])

    assert cli.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert not report["healthy"]
    run, = report["runs"]
    assert run["seconds"] == 5 and run["min_seconds"] == 6
    by_channel = {ch["id"]: ch for ch in run["channels"]}
    assert by_channel["imu.gyro"]["statuses"]["NO_RESPONSE"] == 1
    assert by_channel["radio.heartbeat"]["statuses"]["HEARTBEAT_LOST"] == 1


def test_health_check_can_require_minimum_cadence():
    rows = [row for row in healthy_readings() if row["ts"] % 1000 == 0]
    stream = io.StringIO("\n".join(map(json.dumps, rows)))
    report = check_capture(stream, BENCH, min_rate=0.9)

    assert not report["healthy"]
    channels = {ch["id"]: ch for ch in report["runs"][0]["channels"]}
    assert channels["imu.gyro"]["statuses"] == {"OK": 6}
    assert channels["imu.gyro"]["observed_hz"] == 1
    assert not channels["imu.gyro"]["cadence_ok"]
    assert channels["radio.heartbeat"]["cadence_ok"]
