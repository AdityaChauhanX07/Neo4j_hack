import json
from collections import defaultdict

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
    with relate.connect() as db, path.open(encoding="utf-8") as feed:
        load_topology(db, topology)
        replay(db, feed)
        scores = []
        for run, entries in labels.items():
            entries.sort(key=lambda entry: entry["ts"])
            for index, marker in enumerate(entries):
                cutoff = entries[index + 1]["ts"] if index + 1 < len(entries) else None
                scores.append(_score(db, run, marker, cutoff))
    return scores


def _score(db, run, marker, cutoff):
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
        RETURN c.id AS id, dx.window_from AS first_bad,
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
    return {
        "run": run, "fault": fault, "expected": list(expected),
        "decision_ms": first["first_verdict"] - first["first_bad"] if first else None,
        "latest_verdict_ms": first["latest_verdict"] - first["first_bad"] if first else None,
        "ranked": [row["id"] for row in ranked],
        "baseline": naive["id"] if naive else None,
    }
