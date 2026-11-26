from dataclasses import dataclass
from math import isfinite
from typing import Optional

DEVICE_FAULTS = ("NO_RESPONSE", "OUT_OF_RANGE", "STUCK", "STALE", "HEARTBEAT_LOST")
STUCK_SAMPLES = 10
STALE_PERIODS = 3
HEARTBEAT_TIMEOUT_MS = 3000
UNDERVOLTAGE_RATIO = 0.9


@dataclass(frozen=True)
class Reading:
    run: str
    seq: int
    ts: int
    channel: str
    value: object
    ok: bool
    error: Optional[str] = None
    simulated: Optional[bool] = None

    @classmethod
    def from_record(cls, record):
        reading = cls(*(record[key] for key in ("run", "seq", "ts", "channel", "value", "ok")),
                      error=record.get("error"), simulated=record.get("simulated"))
        if any(not isinstance(name, str) or not name for name in (reading.run, reading.channel)):
            raise ValueError("run and channel must be nonempty strings")
        if any(type(number) is not int or number < 0 for number in (reading.seq, reading.ts)):
            raise ValueError("seq and ts must be nonnegative integers")
        if type(reading.ok) is not bool:
            raise ValueError("ok must be a boolean")
        if reading.simulated is not None and type(reading.simulated) is not bool:
            raise ValueError("simulated must be a boolean or null")
        if reading.error is not None and not isinstance(reading.error, str):
            raise ValueError("error must be a string or null")
        if reading.ok or reading.value is not None:
            values = reading.value if isinstance(reading.value, list) else [reading.value]
            if not values or any(type(value) not in (int, float) or not isfinite(value) for value in values):
                raise ValueError("value must be a finite number or a list of finite numbers")
        return reading


@dataclass(frozen=True)
class Event:
    id: str
    run: str
    ts: int
    channel: str
    status: str
    seq: Optional[int] = None
    value: object = None
    error: Optional[str] = None


@dataclass
class ChannelState:
    last_ts: int
    value: object = None
    repeats: int = 0
    missing: bool = False

    def measure(self, channel, reading):
        if reading.ok or not channel.heartbeat:
            self.last_ts = reading.ts
            self.missing = False
        if reading.ok and reading.value == self.value:
            self.repeats += 1
        else:
            self.repeats = int(reading.ok)
        self.value = reading.value if reading.ok else None

        status = classify(channel, reading, self.repeats)
        return Event(
            f"reading:{reading.run}:{reading.seq}", reading.run, reading.ts,
            channel.id, status, reading.seq, reading.value, reading.error,
        )

    def gap(self, channel, run, before):
        timeout = HEARTBEAT_TIMEOUT_MS if channel.heartbeat else channel.period_ms * STALE_PERIODS
        deadline = self.last_ts + timeout
        if self.missing or deadline >= before:
            return None
        self.missing = True
        self.repeats = 0
        status = "HEARTBEAT_LOST" if channel.heartbeat else "STALE"
        return Event(f"gap:{run}:{channel.id}:{deadline}", run, deadline, channel.id, status)


def classify(channel, reading, repeats):
    if not reading.ok:
        return "NO_RESPONSE"
    value = reading.value
    values = value if isinstance(value, list) else [value]
    if channel.nominal is not None and min(values) < UNDERVOLTAGE_RATIO * channel.nominal:
        return "UNDERVOLTAGE"
    if channel.minimum is not None and min(values) < channel.minimum:
        return "OUT_OF_RANGE"
    if channel.maximum is not None and max(values) > channel.maximum:
        return "OUT_OF_RANGE"
    if channel.noisy and repeats >= STUCK_SAMPLES:
        return "STUCK"
    return "OK"
