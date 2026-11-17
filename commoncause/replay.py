import json
from dataclasses import asdict, replace
from itertools import groupby

from .classify import ChannelState, Reading
from .diagnose import resolve, write_verdict
from .episode import Episode
from .schema import merge_links, merge_nodes, transaction
from .topology import read_channels

OK_INTERVAL_MS = 1000


def records(stream):
    for line_no, line in enumerate(stream, start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if not isinstance(entry, dict):
                raise ValueError("expected a JSON object")
            if entry.get("type") != "fault":
                yield Reading.from_record(entry)
        except (KeyError, ValueError, TypeError, OverflowError) as error:
            raise ValueError(f"Line {line_no}: {error}") from error


def replay(db, stream, *, source="replay", run_id=None):
    run_ids = []
    for recorded_run, readings in groupby(records(stream), key=lambda reading: reading.run):
        if run_id is not None and run_ids:
            raise ValueError("--run can only rename a single recorded run")
        episode_engine = Run(db, run_id or recorded_run, source)
        complete = False
        try:
            for _, batch in groupby(readings, key=lambda reading: reading.ts):
                episode_engine.ingest([replace(item, run=episode_engine.id) for item in batch])
            complete = True
        finally:
            episode_engine.finish(complete)
        run_ids.append(episode_engine.id)
    if not run_ids:
        raise ValueError("No telemetry records")
    return run_ids


class Run:
    def __init__(self, db, run_id, source):
        self.db = db
        self.id = run_id
        self.source = source
        self.channels = read_channels(db)
        self.topology = db.execute("MATCH (t:Topology) RETURN t.sha AS sha").fetchone()
        if not self.channels or self.topology is None:
            raise ValueError("Initialize the store with a topology before ingesting telemetry")
        existing = db.execute("MATCH (r:Run {id: $run}) RETURN r.id AS id", {"run": run_id})
        if existing.fetchone():
            raise ValueError(f"Run {run_id} already exists")
        self.states = {}
        self.last_ts = None
        self.last_seq = -1
        self.saved = {}
        self.episode = None
        self.previous = None
        self.episode_count = 0

    def ingest(self, readings):
        now = readings[0].ts
        if self.last_ts is not None and now < self.last_ts:
            raise ValueError("Telemetry timestamps must be in order within a run")
        seq = self.last_seq
        for reading in readings:
            if reading.seq <= seq:
                raise ValueError("Telemetry seq must increase within a run")
            if reading.channel not in self.channels:
                raise ValueError(f"Unknown channel {reading.channel}")
            seq = reading.seq

        with transaction(self.db):
            if self.last_ts is None:
                merge_nodes(self.db, "Run", [{
                    "id": self.id, "source": self.source, "started": now,
                    "topology_sha": self.topology["sha"],
                }])
                self.states = {key: ChannelState(now) for key in self.channels}

            gaps = [
                self.states[key].gap(channel, self.id, now)
                for key, channel in self.channels.items()
            ]
            gaps = sorted((event for event in gaps if event), key=lambda event: (event.ts, event.channel))
            for at, batch in groupby(gaps, key=lambda event: event.ts):
                self._apply(batch, at)
            samples = (
                self.states[item.channel].measure(self.channels[item.channel], item)
                for item in readings
            )
            self._apply(samples, now)

        self.last_ts = now
        self.last_seq = seq

    def _apply(self, events, now):
        kept = []
        previous = []
        for event in events:
            if event.status != "OK" and self.episode is None:
                self.episode_count += 1
                self.episode = Episode(f"dx:{self.id}:{self.episode_count}", event.ts)
            if self.episode is not None:
                self.episode.observe(event)
            prior = self.saved.get(event.channel)
            closing = self.episode is not None and self.episode.resolved_at is event
            if self._keep(event, prior) or closing:
                kept.append(event)
                if prior:
                    previous.append([prior.id, event.id])
                self.saved[event.channel] = event

        if kept:
            merge_nodes(self.db, "Event", [
                {key: value for key, value in asdict(event).items() if key != "channel"}
                for event in kept
            ])
            merge_links(self.db, "Event", "ON", "TelemetryChannel", [
                [event.id, event.channel] for event in kept
            ])
            merge_links(self.db, "Event", "NEXT", "Event", previous)
            merge_links(self.db, "Event", "SHOWS", "Symptom", [
                [event.id, event.status] for event in kept if event.status != "OK"
            ])

        if self.episode and self.episode.ready(now):
            write_verdict(self.db, self.episode, self.id, now, self.previous)
        if self.episode and self.episode.written and self.episode.resolved_at:
            resolve(self.db, self.episode)
            self.previous = self.episode.id
            self.episode = None

    @staticmethod
    def _keep(event, prior):
        return (
            event.status != "OK"
            or prior is None
            or prior.status != event.status
            or event.ts - prior.ts >= OK_INTERVAL_MS
        )

    def finish(self, complete):
        if self.last_ts is not None:
            self.db.execute(
                "MATCH (r:Run {id: $run}) SET r.ended = $ended, r.complete = $complete",
                {"run": self.id, "ended": self.last_ts, "complete": complete},
            )
