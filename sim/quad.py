import json

READINGS = {
    "fc.load": 41,
    "compass.heading": 81.4,
    "barometer.pressure": 1009,
    "gyro.rate": [0.2, 0.3, -0.1],
    "gps.satellites": 11,
    "telemetry.seq": 0,
    "power.bec_voltage": 5.03,
    **{f"esc.{index}.current": 6.1 for index in range(1, 5)},
    **{f"motor.{index}.rpm": 12140 for index in range(1, 5)},
}

FAULTS = {
    "bec-brownout": (
        "BEC_5V",
        {"fc.load", "compass.heading", "barometer.pressure",
         "gyro.rate", "gps.satellites", "telemetry.seq"},
    ),
    "compass-bus-failure": ("I2C-FC", {"compass.heading", "barometer.pressure"}),
    "esc-3-dropout": ("esc.3", {"esc.3.current", "motor.3.rpm"}),
}


def records():
    for number, (fault, (expected, failed)) in enumerate(FAULTS.items()):
        run = f"quad-{fault}"
        start = 1794873600000 + number * 10000
        seq = 0
        for age in range(0, 3501, 500):
            ts = start + age
            if age in (1000, 2500):
                seq += 1
                yield {
                    "run": run, "seq": seq, "ts": ts, "type": "fault",
                    "fault": fault, "expected": expected,
                    "action": "inject" if age == 1000 else "clear",
                }
            active = 1000 <= age < 2500
            for channel, nominal in READINGS.items():
                ok = not (active and channel in failed)
                value = age // 500 if channel == "telemetry.seq" else nominal
                if active and channel == "power.bec_voltage" and fault == "bec-brownout":
                    value = 3.4
                seq += 1
                yield {
                    "run": run, "seq": seq, "ts": ts, "channel": channel,
                    "value": value if ok else None, "ok": ok,
                    "error": None if ok else "timeout",
                }


if __name__ == "__main__":
    for row in records():
        print(json.dumps(row, separators=(",", ":")))
