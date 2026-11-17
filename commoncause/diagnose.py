from .classify import DEVICE_FAULTS
from .schema import merge_links, read_asset

RANK = read_asset("queries", "rank.cypher")
WRITE = read_asset("queries", "write_diagnosis.cypher")

MONITORED = """
MATCH (e:Event {run: $run, status: 'UNDERVOLTAGE'})-[:ON]->
      (:TelemetryChannel)-[:MONITORS]->(c:Regulator)
WHERE e.ts >= $from AND e.ts <= $to
WITH c, min(e.ts) AS since
RETURN c.id AS suspect, 'Regulator' AS kind, 0 AS covered, 0 AS contradicted,
       1.0 AS score, [] AS covered_devices
ORDER BY since, suspect
"""

MATCH_MODE = """
MATCH (c {id: $suspect})<-[:APPLIES_TO]-(fm:FailureMode)-[:PRODUCES]->(sym:Symptom)
WHERE sym.code IN $symptoms
WITH fm, count(DISTINCT sym) AS matched
WHERE fm.id <> 'connector-intermittent' OR $intermittent
RETURN fm.id AS mode
ORDER BY matched DESC, mode
LIMIT 1
"""


def rank_params(run, start, now):
    return {
        "run": run, "from": start, "to": now,
        "device_faults": list(DEVICE_FAULTS), "exclude_devices": [],
    }


def rank(db, run, start, now):
    params = rank_params(run, start, now)
    ranked = db.execute(RANK, params).fetchall()
    if not ranked:
        monitored = db.execute(MONITORED, params).fetchall()
        return monitored[:3], _confidence(monitored)

    confidence = _confidence(ranked)
    suspects = []
    while ranked and len(suspects) < 3:
        top = ranked[0]
        suspects.append(top)
        if top["score"] == 1.0 or len(suspects) == 3:
            break
        params["exclude_devices"].extend(top["covered_devices"])
        ranked = db.execute(RANK, params).fetchall()
    return suspects, confidence


def _confidence(ranked):
    if not ranked:
        return "low"
    top = ranked[0]["score"]
    runner_up = ranked[1]["score"] if len(ranked) > 1 else 0
    if top == 1.0 and top - runner_up >= 0.25:
        return "high"
    return "medium" if top >= 0.75 else "low"


def write_verdict(db, episode, run, now, previous, channels):
    suspects, confidence = rank(db, run, episode.opened, now)
    if not suspects:
        return
    intermittent_devices = {channels[key].device for key in episode.intermittent}
    if suspects[0]["suspect"] in intermittent_devices and confidence == "high":
        confidence = "medium"
    db.execute("""
        MATCH (:Diagnosis {id: $id})-[r:SUSPECTS|MATCHES]->()
        DELETE r
    """, {"id": episode.id})
    db.execute(WRITE, {
        "id": episode.id, "run": run, "now": now, "from": episode.opened,
        "confidence": confidence,
        "ranked": [{**suspect, "rank": index} for index, suspect in enumerate(suspects, 1)],
    })
    for index, suspect in enumerate(suspects, start=1):
        mode = db.execute(MATCH_MODE, {
            "suspect": suspect["suspect"],
            "symptoms": sorted(set(episode.statuses.values())),
            "intermittent": suspect["suspect"] in intermittent_devices,
        }).fetchone()
        if mode:
            db.execute("""
                MATCH (dx:Diagnosis {id: $id}), (fm:FailureMode {id: $mode})
                CREATE (dx)-[:MATCHES {rank: $rank, suspect: $suspect}]->(fm)
            """, {
                "id": episode.id, "mode": mode["mode"],
                "rank": index, "suspect": suspect["suspect"],
            })
    merge_links(db, "Diagnosis", "BASED_ON", "Event", [
        [episode.id, event.id] for event in episode.evidence.values()
    ])
    if previous:
        merge_links(db, "Diagnosis", "FOLLOWS", "Diagnosis", [[episode.id, previous]])
    episode.dirty = False
    episode.written = True


def resolve(db, episode):
    db.execute("MATCH (dx:Diagnosis {id: $id}) SET dx.state = 'resolved'", {"id": episode.id})
    merge_links(db, "Diagnosis", "RESOLVED_AT", "Event", [[episode.id, episode.resolved_at.id]])
