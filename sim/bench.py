import argparse
import json
import random
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


def records(only=None, *, seed=None, repeats=1):
    if repeats < 1:
        raise ValueError("Repeats must be positive")
    rng = random.Random(seed) if seed is not None else None
    rows = list(map(json.loads, FIXTURE.read_text().splitlines()))
    epoch = rows[0]["ts"]
    nominal = {
        row["channel"]: row["value"] for row in rows
        if row["ts"] == epoch and "channel" in row
    }
    cases = {"healthy": ([], set(), set())} if only == "healthy" else CASES
    for repeat in range(repeats):
        for index, (fault, (expected, failed, silent)) in enumerate(cases.items()):
            if only is not None and fault != only:
                continue
            run = f"bench-fixture-{fault.lower()}"
            if rng is not None:
                run = f"bench-seed-{seed}-{repeat + 1}-{fault.lower()}"
            elif repeats > 1:
                run += f"-{repeat + 1}"
            start = epoch + (repeat * len(cases) + index) * (20000 if rng else 10000)
            injected = rng.randrange(1000, 2501, 500) if rng else 1000
            cleared = injected + (rng.randrange(4000, 8001, 500) if rng else 5000)
            end = cleared + (rng.randrange(3000, 5001, 500) if rng else 2000)
            seq = 0
            for age in range(0, end + 1, 500):
                # Jitter is shared by each frame so readings stay in time order.
                ts = start + age + (rng.randint(-75, 75) if rng and age else 0)
                if fault != "healthy" and age in (injected, cleared):
                    seq += 1
                    yield {
                        "run": run, "seq": seq, "ts": ts, "type": "fault",
                        "fault": fault, "expected": expected,
                        "action": "inject" if age == injected else "clear",
                    }
                active = injected <= age < cleared
                samples = list(nominal.items())
                if rng:
                    rng.shuffle(samples)
                for channel, value in samples:
                    if channel == "radio.heartbeat":
                        if age % 1000:
                            continue
                        value = age // 1000
                    if active and channel in silent:
                        continue
                    ok = not (active and channel in failed and (fault != "F8" or age % 1000 == 0))
                    if active and fault in {"F1", "F5", "F9"} and channel == "eps.regb.voltage":
                        value = 0.16
                    if rng and ok and channel != "radio.heartbeat":
                        value = perturb(value, rng)
                    seq += 1
                    yield {
                        "run": run, "seq": seq, "ts": ts, "channel": channel,
                        "value": value if ok else None, "ok": ok,
                        "error": None if ok else "EREMOTEIO",
                    }


def perturb(value, rng):
    if isinstance(value, list):
        return [perturb(item, rng) for item in value]
    return round(value + rng.uniform(-0.02, 0.02) * max(abs(value), 1), 6)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate simulated CubeSat telemetry")
    parser.add_argument("--seed", type=int, help="vary timing and readings with a repeatable seed")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--fault", choices=[*CASES, "healthy"])
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    for row in records(args.fault, seed=args.seed, repeats=args.repeats):
        print(json.dumps(row, separators=(",", ":")))
