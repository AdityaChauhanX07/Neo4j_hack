import sys

from .schema import merge_links, merge_nodes, transaction


class VirtualRecovery:
    def __init__(self, bench, *, verify_ms=3000, output=None):
        self.bench = bench
        self.verify_ms = verify_ms
        self.output = output or sys.stderr
        self.attempted = set()
        self.pending = None

    def observe(self, db, run):
        if not run.simulated:
            raise ValueError("Automatic recovery is restricted to simulated telemetry")
        if self.pending:
            attempt = self.pending
            resolution = db.execute("""
                MATCH (dx:Diagnosis {id: $id})-[:RESOLVED_AT]->(e:Event)
                WHERE dx.state = 'resolved' AND e.ts > $after
                RETURN e.id AS id, e.ts AS ts
            """, {"id": attempt["diagnosis"], "after": attempt["ts"]}).fetchone()
            channels = [channel.id for channel in run.channels.values()
                        if self.bench.board.devices[channel.device].bus == attempt["target"]]
            healthy = all(run.latest.get(key) is not None
                          and run.latest[key].status == "OK" and run.latest[key].ts > attempt["ts"]
                          for key in channels)
            if resolution and healthy:
                self._finish(db, run.last_ts, "verified", resolution["id"])
            elif run.last_ts >= attempt["ts"] + self.verify_ms:
                self._finish(db, run.last_ts, "not_recovered")
            return

        candidates = db.execute("""
            MATCH (dx:Diagnosis {run: $run, state: 'open'})-[s:SUSPECTS]->(c)
            RETURN dx.id AS diagnosis, dx.confidence AS confidence, c.id AS target,
                   labels(c)[0] AS kind, s.contradicted AS contradicted
            ORDER BY dx.ts DESC, s.rank
        """, {"run": run.id}).fetchall()
        if len(candidates) != 1:
            return
        candidate = candidates[0]
        if (candidate["diagnosis"] in self.attempted or candidate["confidence"] != "high"
                or candidate["kind"] != "Bus" or candidate["contradicted"]
                or candidate["target"] not in self.bench.board.i2c):
            return
        procedure = db.execute("""
            MATCH (:Diagnosis {id: $id})-[m:MATCHES]->(fm:FailureMode {id: 'bus-held-low'})
                  -[:RECOVERED_BY]->(rp:RecoveryProcedure)
            WHERE m.suspect = $target
            RETURN rp.id AS id
        """, {"id": candidate["diagnosis"], "target": candidate["target"]}).fetchone()
        if not procedure:
            return
        attempt = {
            "id": f"recovery:{candidate['diagnosis']}:1", "diagnosis": candidate["diagnosis"],
            "run": run.id, "target": candidate["target"], "ts": run.last_ts,
            "action": "i2c-bus-clear", "procedure": procedure["id"],
            "simulated": True, "state": "awaiting_telemetry",
        }
        with transaction(db):
            merge_nodes(db, "RecoveryAttempt", [attempt])
            merge_links(db, "Diagnosis", "ATTEMPTED", "RecoveryAttempt", [[candidate["diagnosis"], attempt["id"]]])
            merge_links(db, "RecoveryAttempt", "TARGETS", "Bus", [[attempt["id"], candidate["target"]]])
            merge_links(db, "RecoveryAttempt", "USES", "RecoveryProcedure", [[attempt["id"], procedure["id"]]])
        self.attempted.add(candidate["diagnosis"])
        self.pending = attempt
        self.bench.clear_bus(candidate["target"])
        print(f"Simulated recovery: {candidate['target']} bus clear; awaiting telemetry", file=self.output)

    def _finish(self, db, timestamp, state, event=None):
        with transaction(db):
            db.execute("""
                MATCH (a:RecoveryAttempt {id: $id}) SET a.state = $state, a.finished = $ts
            """, {"id": self.pending["id"], "state": state, "ts": timestamp})
            if event:
                merge_links(db, "RecoveryAttempt", "VERIFIED_BY", "Event", [[self.pending["id"], event]])
        print(f"Simulated recovery: {self.pending['target']} {state}", file=self.output)
        self.pending = None

    def finish(self, db, timestamp):
        if self.pending:
            self._finish(db, timestamp, "unverified")
