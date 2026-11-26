import json
from collections import defaultdict
from itertools import groupby

import relate

from .classify import DEVICE_FAULTS
from .replay import replay
from .topology import load_topology

EXPECTED = {
    "F1": ("REG_B",),
    "F2": ("I2C-1",),
    "F3": ("I2C-3",),
    "F4": ("sun2",),
    "F5": ("RAIL_5V",),
    "F6": ("UART0",),
    "F7": ("drv.imu",),
    "F9": ("REG_B", "I2C-3"),
}


def matrix(path, topology):
    labels = defaultdict(list)
    with path.open(encoding="utf-8") as feed:
        for line in feed:
            if not line.strip():
                continue
            marker = json.loads(line)
            if marker.get("type") == "fault" and marker.get("action") == "inject":
                labels[marker["run"]].append(marker)

    if not labels:
        raise ValueError("No fault injection markers")
    history = defaultdict(list)

    def remember_verdict(db, session):
        rows = db.execute("""
            MATCH (dx:Diagnosis {run: $run})-[s:SUSPECTS]->(c)
            RETURN dx.id AS diagnosis, c.id AS suspect
            ORDER BY dx.id, s.rank
        """, {"run": session.id}).fetchall()
        for diagnosis_id, suspects in groupby(rows, key=lambda row: row["diagnosis"]):
            revisions = history[diagnosis_id]
            ranked = [row["suspect"] for row in suspects]
            if not revisions or revisions[-1][1] != ranked:
                revisions.append((session.last_ts, ranked))

    with relate.connect() as db, path.open(encoding="utf-8") as feed:
        load_topology(db, topology)
        # SUSPECTS is replaced on each update, so observe the committed frames.
        replay(db, feed, on_frame=remember_verdict)
        scores = []
        for run, entries in labels.items():
            entries.sort(key=lambda entry: entry["ts"])
            for index, marker in enumerate(entries):
                cutoff = entries[index + 1]["ts"] if index + 1 < len(entries) else None
                scores.append(_score(db, run, marker, cutoff, history))
    return scores


def _score(db, run, marker, cutoff, history):
    fault = marker["fault"]
    expected = marker.get("expected", EXPECTED.get(fault))
    if isinstance(expected, str):
        expected = [expected]
    if not isinstance(expected, (list, tuple)) or not expected or any(
        not isinstance(item, str) or not item for item in expected
    ):
        raise ValueError(f"Injection {fault} needs an expected component")
    params = {"run": run, "start": marker["ts"], "end": cutoff, "faults": list(DEVICE_FAULTS)}
    ranked = db.execute("""
        MATCH (dx:Diagnosis {run: $run})
        WHERE dx.window_from >= $start AND ($end IS NULL OR dx.window_from < $end)
        WITH dx ORDER BY dx.window_from LIMIT 1
        MATCH (dx)-[s:SUSPECTS]->(c)
        RETURN c.id AS id, dx.id AS diagnosis, dx.window_from AS first_bad,
               coalesce(dx.first_verdict_ts, dx.ts) AS first_verdict, dx.ts AS latest_verdict
        ORDER BY s.rank
    """, params).fetchall()
    naive = db.execute("""
        MATCH (e:Event {run: $run})-[:ON]->(:TelemetryChannel)-[:READS]->(d:Device)
        WHERE e.ts >= $start AND ($end IS NULL OR e.ts < $end) AND e.status IN $faults
        RETURN d.id AS id
        ORDER BY e.ts, e.seq, e.id
        LIMIT 1
    """, params).fetchone()
    first = ranked[0] if ranked else None
    correct_at = None
    if first:
        correct_at = next((
            observed for observed, suspects in history[first["diagnosis"]]
            if (cutoff is None or observed < cutoff)
            and suspects[:1] == list(expected[:1]) and set(suspects) == set(expected)
        ), None)
    return {
        "run": run, "fault": fault, "expected": list(expected),
        "decision_ms": first["first_verdict"] - first["first_bad"] if first else None,
        "latest_verdict_ms": first["latest_verdict"] - first["first_bad"] if first else None,
        "first_correct_ms": correct_at - first["first_bad"] if correct_at is not None else None,
        "ranked": [row["id"] for row in ranked],
        "baseline": naive["id"] if naive else None,
    }
