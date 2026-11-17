from pathlib import Path

import pytest
import relate

BENCH = Path(__file__).with_name("bench.cypher").read_text(encoding="utf-8")
RANK = (Path(__file__).resolve().parents[1] / "queries" / "rank.cypher").read_text(
    encoding="utf-8"
)
DEVICE_FAULTS = ["NO_RESPONSE", "OUT_OF_RANGE", "STUCK", "STALE", "HEARTBEAT_LOST"]
RECORD = """
UNWIND $readings AS reading
MATCH (ch:TelemetryChannel {id: reading.channel})
CREATE (:Event {ts: reading.ts, status: reading.status})-[:ON]->(ch)
"""


def test_regulator_input_loss():
    samples = [
        ("imu.gyro", 1000, "NO_RESPONSE"),
        ("imu.gyro", 1500, "NO_RESPONSE"),
        ("imu.accel", 1500, "NO_RESPONSE"),
        ("mag.field", 1000, "NO_RESPONSE"),
        ("eps.regb.voltage", 1000, "UNDERVOLTAGE"),
        ("thermal.temp", 999, "NO_RESPONSE"),
        ("thermal.temp", 1000, "OK"),
        ("sun1.lux", 2000, "NO_RESPONSE"),
        ("sun2.lux", 1000, "OK"),
        ("payload.temp", 1000, "OK"),
        ("radio.heartbeat", 1000, "OK"),
    ]
    with relate.connect() as db:
        db.execute(BENCH)
        db.execute(
            RECORD,
            {
                "readings": [
                    {"channel": channel, "ts": ts, "status": status}
                    for channel, ts, status in samples
                ]
            },
        )
        ranked = db.execute(
            RANK, {"from": 1000, "to": 2000, "device_faults": DEVICE_FAULTS}
        ).fetchall()

    assert ranked[0] == {
        "suspect": "REG_B",
        "kind": "Regulator",
        "covered": 3,
        "contradicted": 0,
        "score": 1.0,
    }
    assert ranked[1]["suspect"] == "RAIL_5V"
    assert ranked[1]["contradicted"] == 1
    assert ranked[1]["score"] == pytest.approx(0.75)
    bus = next(row for row in ranked if row["suspect"] == "I2C-1")
    assert (bus["covered"], bus["contradicted"]) == (2, 2)
    assert bus["score"] == pytest.approx(1 / 3)
    assert any(row["suspect"] == "imu" for row in ranked)
