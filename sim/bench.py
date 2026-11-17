import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "recordings" / "f1-fixture.jsonl"
REG_B = {"imu.gyro", "imu.accel", "mag.field", "sun1.lux"}
BUS_1 = {"imu.gyro", "imu.accel", "mag.field", "eps.regb.voltage", "eps.regb.current", "thermal.temp"}
BUS_3 = {"sun1.lux", "sun2.lux", "payload.temp", "payload.pressure"}

CASES = {
    "F1": (["REG_B"], REG_B, set()),
    "F2": (["I2C-1"], BUS_1, set()),
    "F3": (["I2C-3"], BUS_3, set()),
    "F4": (["sun2"], {"sun2.lux"}, set()),
    "F5": (["RAIL_5V"], REG_B, {"radio.heartbeat"}),
    "F6": (["UART0"], set(), {"radio.heartbeat"}),
    "F7": (["drv.imu"], set(), {"imu.gyro"}),
    "F8": (["sun2"], {"sun2.lux"}, set()),
    "F9": (["REG_B", "I2C-3"], REG_B | BUS_3, set()),
}


def records(only=None):
    rows = list(map(json.loads, FIXTURE.read_text().splitlines()))
    epoch = rows[0]["ts"]
    nominal = {
        row["channel"]: row["value"] for row in rows
        if row["ts"] == epoch and "channel" in row
    }
    for index, (fault, (expected, failed, silent)) in enumerate(CASES.items()):
        if only is not None and fault != only:
            continue
        run = f"bench-fixture-{fault.lower()}"
        start = epoch + index * 10000
        seq = 0
        for age in range(0, 8001, 500):
            ts = start + age
            if age in (1000, 6000):
                seq += 1
                yield {
                    "run": run, "seq": seq, "ts": ts, "type": "fault",
                    "fault": fault, "expected": expected,
                    "action": "inject" if age == 1000 else "clear",
                }
            active = 1000 <= age < 6000
            for channel, value in nominal.items():
                if channel == "radio.heartbeat":
                    if age % 1000:
                        continue
                    value = age // 1000
                if active and channel in silent:
                    continue
                ok = not (active and channel in failed and (fault != "F8" or age % 1000 == 0))
                if active and fault in {"F1", "F5", "F9"} and channel == "eps.regb.voltage":
                    value = 0.16
                seq += 1
                yield {
                    "run": run, "seq": seq, "ts": ts, "channel": channel,
                    "value": value if ok else None, "ok": ok,
                    "error": None if ok else "EREMOTEIO",
                }


if __name__ == "__main__":
    for row in records():
        print(json.dumps(row, separators=(",", ":")))
