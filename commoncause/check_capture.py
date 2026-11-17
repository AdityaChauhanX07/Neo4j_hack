from collections import Counter
from dataclasses import dataclass, field
from itertools import chain, groupby
from math import isfinite
from typing import Optional

import relate

from .classify import ChannelState
from .replay import records
from .topology import load_topology, read_channels


@dataclass
class ChannelCounts:
    last_ts: int
    first_ts: Optional[int] = None
    readings: int = 0
    max_gap: int = 0
    statuses: Counter = field(default_factory=Counter)

    def observe(self, event):
        if self.first_ts is None:
            self.first_ts = event.ts
        self.max_gap = max(self.max_gap, event.ts - self.last_ts)
        self.last_ts = event.ts
        self.readings += 1
        self.statuses[event.status] += 1

    def summary(self, channel, end, min_rate):
        span = self.last_ts - self.first_ts if self.first_ts is not None else 0
        rate = (self.readings - 1) * 1000 / span if span else None
        expected = 1000 / channel.period_ms
        cadence_ok = min_rate == 0 or (rate is not None and rate >= expected * min_rate)
        return {
            "id": channel.id,
            "readings": self.readings,
            "expected_hz": expected,
            "observed_hz": round(rate, 2) if rate is not None else None,
            "cadence_ok": cadence_ok,
            "max_gap_ms": max(self.max_gap, end - self.last_ts),
            "statuses": dict(sorted(self.statuses.items())),
            "healthy": cadence_ok and bool(self.readings) and self.statuses.keys() == {"OK"},
        }


def check_capture(stream, topology, *, min_seconds=0, min_rate=0):
    if not isfinite(min_seconds) or min_seconds < 0:
        raise ValueError("Minimum duration must be a finite, nonnegative number")
    if not 0 <= min_rate <= 1:
        raise ValueError("Minimum cadence fraction must be between 0 and 1")
    with relate.connect() as db:
        load_topology(db, topology)
        channels = read_channels(db)
    if not channels:
        raise ValueError("The topology has no telemetry channels")

    summaries = []
    seen = set()
    for run, readings in groupby(records(stream), key=lambda reading: reading.run):
        if run in seen:
            raise ValueError(f"Readings for {run} must be grouped together")
        seen.add(run)
        summaries.append(_check_run(run, readings, channels, min_seconds, min_rate))
    if not summaries:
        raise ValueError("No telemetry records")
    return {"healthy": all(run["healthy"] for run in summaries), "runs": summaries}


def _check_run(run, readings, channels, min_seconds, min_rate):
    first = next(readings)
    start = first.ts
    latest = start
    seq = -1
    counts = {key: ChannelCounts(start) for key in channels}
    states = {key: ChannelState(start) for key in channels}

    for reading in chain((first,), readings):
        if reading.ts < latest or reading.seq <= seq:
            raise ValueError(f"Telemetry sequence or timestamp is out of order in {run}")
        if reading.channel not in channels:
            raise ValueError(f"Unknown channel {reading.channel} in {run}")
        if reading.ts != latest:
            for key, state in states.items():
                gap = state.gap(channels[key], run, reading.ts)
                if gap:
                    counts[key].statuses[gap.status] += 1
        channel = channels[reading.channel]
        event = states[reading.channel].measure(channel, reading)
        counts[reading.channel].observe(event)
        latest, seq = reading.ts, reading.seq

    span = (latest - start) / 1000
    reports = [counts[key].summary(channels[key], latest, min_rate) for key in sorted(channels)]
    long_enough = span >= min_seconds
    return {
        "run": run,
        "seconds": span,
        "min_seconds": min_seconds,
        "min_rate": min_rate,
        "healthy": long_enough and all(report["healthy"] for report in reports),
        "channels": reports,
    }


def show_check(report):
    for run in report["runs"]:
        result = "healthy" if run["healthy"] else "check failed"
        print(f"{run['run']}  {run['seconds']:.3f} seconds  {result}")
        if run["seconds"] < run["min_seconds"]:
            print(f"Need at least {run['min_seconds']:g} seconds of readings")
        for channel in run["channels"]:
            rate = channel["observed_hz"]
            observed = f"{rate:.2f}" if rate is not None else "-"
            statuses = ", ".join(
                f"{status}={count}" for status, count in channel["statuses"].items()
            ) or "no readings"
            cadence = "" if channel["cadence_ok"] else "  below cadence"
            print(f"{channel['id']:<18} {channel['readings']:>5} readings  "
                  f"{observed}/{channel['expected_hz']:.2f} Hz  "
                  f"max gap {channel['max_gap_ms']} ms  {statuses}{cadence}")
