from dataclasses import dataclass, field

SETTLE_MS = 1000
RECOVERY_SAMPLES = 3


@dataclass
class Episode:
    id: str
    opened: int
    evidence: dict = field(default_factory=dict)
    statuses: dict = field(default_factory=dict)
    recovery: dict = field(default_factory=dict)
    dirty: bool = True
    written: bool = False
    resolved_at: object = None

    def observe(self, event):
        channel = event.channel
        if event.status != "OK":
            self.evidence.setdefault(channel, event)
            if self.statuses.get(channel) != event.status or self.recovery.get(channel, 0) >= RECOVERY_SAMPLES:
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
