from dataclasses import replace

import pytest

from commoncause.classify import ChannelState, Reading, classify
from commoncause.topology import Channel

SENSOR = Channel("sensor", "imu", 500, -2, 2, True, False, None, None, "I2C-1", "drv.imu")
READING = Reading("bench", 1, 1000, "sensor", [0, 1, 0], True)


@pytest.mark.parametrize(
    ("channel", "reading", "repeats", "status"),
    [
        (SENSOR, READING, 1, "OK"),
        (SENSOR, replace(READING, ok=False, value=None, error="EREMOTEIO"), 1, "NO_RESPONSE"),
        (SENSOR, replace(READING, value=[1, 3, 1]), 1, "OUT_OF_RANGE"),
        (SENSOR, READING, 10, "STUCK"),
        (replace(SENSOR, nominal=3.3), replace(READING, value=2.9), 1, "UNDERVOLTAGE"),
    ],
)
def test_classification(channel, reading, repeats, status):
    assert classify(channel, reading, repeats) == status


@pytest.mark.parametrize(("heartbeat", "deadline", "status"), [
    (False, 2500, "STALE"),
    (True, 4000, "HEARTBEAT_LOST"),
])
def test_gap_emitted_once_until_next_sample(heartbeat, deadline, status):
    channel = replace(SENSOR, heartbeat=heartbeat)
    state = ChannelState(1000)
    assert state.gap(channel, "bench", deadline) is None
    event = state.gap(channel, "bench", deadline + 1)
    assert (event.ts, event.status) == (deadline, status)
    assert state.gap(channel, "bench", deadline + 2) is None
    state.measure(channel, replace(READING, ts=deadline + 2))
    assert state.gap(channel, "bench", deadline * 2) is not None
