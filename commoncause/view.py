import sys

from .schema import read_asset

RECOVERY = read_asset("queries", "recovery.cypher")


def diagnosis(db, diagnosis_id=None):
    verdict = db.execute("""
        MATCH (dx:Diagnosis)
        WHERE $id IS NULL OR dx.id = $id
        RETURN dx.id AS id, dx.run AS run, dx.ts AS ts, dx.window_from AS window_from,
               dx.window_to AS window_to, dx.state AS state, dx.confidence AS confidence
        ORDER BY ts DESC, id DESC
        LIMIT 1
    """, {"id": diagnosis_id}).fetchone()
    if verdict is None:
        return None

    params = {"id": verdict["id"]}
    verdict["suspects"] = db.execute("""
        MATCH (dx:Diagnosis {id: $id})-[s:SUSPECTS]->(c)
        RETURN s.rank AS rank, c.id AS id, labels(c)[0] AS kind, s.score AS score,
               s.covered AS covered, s.contradicted AS contradicted
        ORDER BY rank
    """, params).fetchall()
    verdict["evidence"] = db.execute("""
        MATCH (dx:Diagnosis {id: $id})-[:BASED_ON]->(e:Event)-[:ON]->(ch:TelemetryChannel)
        RETURN e.id AS id, e.ts AS ts, ch.id AS channel, e.status AS status,
               e.value AS value, e.error AS error
        ORDER BY ts, id
    """, params).fetchall()
    verdict["recovery"] = db.execute(RECOVERY, params).fetchall()
    verdict["resolution"] = db.execute("""
        MATCH (dx:Diagnosis {id: $id})-[:RESOLVED_AT]->(e:Event)
        RETURN e.id AS id, e.ts AS ts
    """, params).fetchone()
    return verdict


def summarize(verdict):
    lines = [f"{verdict['id']}  {verdict['state']}  {verdict['confidence']} confidence"]
    for suspect in verdict["suspects"]:
        lines.append(
            f"{suspect['rank']}. {suspect['id']} ({suspect['kind']})  "
            f"{suspect['score']:.2f}  covers {suspect['covered']}  "
            f"contradicted by {suspect['contradicted']}"
        )
    return "\n".join(lines)


def explain(verdict):
    lines = [summarize(verdict)]
    for event in verdict["evidence"]:
        reading = event["value"] if event["value"] is not None else event["error"]
        detail = f" ({reading})" if reading is not None else ""
        lines.append(f"{event['channel']}  {event['status']}{detail}  [{event['id']}]")
    for mode in verdict["recovery"]:
        lines.append(f"{mode['suspect']}  {mode['failure_mode']} [{mode['mode_id']}]")
        lines.append(f"{mode['procedure']} [{mode['procedure_id']}]")
        lines.extend(f"  - {step}" for step in mode["steps"])
    if verdict["resolution"]:
        lines.append(f"Resolved at [{verdict['resolution']['id']}]")
    return "\n".join(lines)


def live_view():
    last = None

    def update(db):
        nonlocal last
        verdict = diagnosis(db)
        if verdict:
            current = summarize(verdict)
            if current != last:
                print(current, file=sys.stderr, flush=True)
            last = current

    return update
