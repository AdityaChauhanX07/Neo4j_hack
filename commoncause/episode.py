from dataclasses import dataclass, field

from .classify import DEVICE_FAULTS

SETTLE_MS = 1000
RECOVERY_SAMPLES = 3


@dataclass
class Episode:
    id: str
    opened: int
    evidence: dict = field(default_factory=dict)
    statuses: dict = field(default_factory=dict)
    recovery: dict = field(default_factory=dict)
    intermittent: set = field(default_factory=set)
    healthy_devices: set = field(default_factory=set)
    failed_devices: set = field(default_factory=set)
    dirty: bool = True
    written: bool = False
    resolved_at: object = None

    def observe(self, event, device=None):
        channel = event.channel
        device = device or channel
        if event.status in DEVICE_FAULTS:
            self.failed_devices.add(device)
        elif event.status in {"OK", "UNDERVOLTAGE"} and device not in self.healthy_devices:
            self.healthy_devices.add(device)
            # A newly observed healthy device can rule out a shared dependency.
            if device not in self.failed_devices:
                self.dirty = True
        if event.status != "OK":
            self.evidence.setdefault(channel, event)
            previous = self.statuses.get(channel)
            streak = self.recovery.get(channel, 0)
            if (
                previous == event.status == "NO_RESPONSE"
                and 0 < streak < RECOVERY_SAMPLES
                and channel not in self.intermittent
            ):
                self.intermittent.add(channel)
                self.dirty = True
            if previous != event.status or streak >= RECOVERY_SAMPLES:
                self.dirty = True
            self.statuses[channel] = event.status
            self.recovery[channel] = 0
            self.resolved_at = None
        elif channel in self.recovery:
            self.recovery[channel] += 1
            if self.resolved_at is None and all(
                streak >= RECOVERY_SAMPLES for streak in self.recovery.values()
            ):
                self.resolved_at = event

    def ready(self, now):
        return self.dirty and now >= self.opened + SETTLE_MS
