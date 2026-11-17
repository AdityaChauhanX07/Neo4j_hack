import sys
from collections import defaultdict

from .classify import DEVICE_FAULTS
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
    last_run = None
    previous_status = None
    previous_verdict = None
    wiring = []

    def update(db, run):
        nonlocal last_run, previous_status, previous_verdict, wiring
        if run.id != last_run:
            wiring = db.execute("""
                MATCH (d:Device)
                OPTIONAL MATCH (d)-[:POWERED_BY]->(supply)
                OPTIONAL MATCH (d)-[:ON_BUS]->(bus:Bus)
                RETURN d.id AS device, supply.id AS supply, bus.id AS bus
                ORDER BY device
            """).fetchall()
            last_run = run.id
            previous_status = None
            previous_verdict = None

        devices = defaultdict(set)
        monitors = set()
        for key, event in run.latest.items():
            channel = run.channels[key]
            if event.status == "UNDERVOLTAGE":
                monitors.add(channel.monitor)
                devices[channel.device].add("OK")
            else:
                devices[channel.device].add(event.status)

        status = []
        affected = []
        for row in wiring:
            device = row["device"]
            observed = devices[device]
            failures = observed.intersection(DEVICE_FAULTS)
            health = ", ".join(sorted(failures or observed)) or "UNKNOWN"
            connections = ", ".join(part for part in (row["supply"], row["bus"]) if part)
            status.append(f"{device:<10} {health:<20} {connections}".rstrip())
            if failures:
                affected.append(device)
        status.extend(f"{part}  UNDERVOLTAGE" for part in sorted(monitors))
        if status != previous_status:
            print(f"Run {run.id}", *status, sep="\n", file=sys.stderr, flush=True)
            previous_status = status

        if run.episode or run.previous:
            verdict = diagnosis(db, run.episode.id if run.episode else run.previous)
            if verdict:
                current = summarize(verdict)
                if current != previous_verdict:
                    print(current, file=sys.stderr, flush=True)
                    for suspect in verdict["suspects"]:
                        _show_paths(db, suspect["id"], affected)
                    previous_verdict = current

    return update


def _show_paths(db, suspect, affected):
    paths = db.execute("""
        MATCH p = (d:Device)-[:POWERED_BY|FED_BY|ON_BUS*0..4]->(c {id: $id})
        WHERE d.id IN $devices
        RETURN [n IN nodes(p) | n.id] AS path
        ORDER BY d.id, length(p)
        UNION
        MATCH (c:Driver {id: $id})-[:CONTROLS]->(d:Device)
        WHERE d.id IN $devices
        RETURN [d.id, c.id] AS path
    """, {"id": suspect, "devices": affected})
    for row in paths:
        print("  " + " -> ".join(row["path"]), file=sys.stderr, flush=True)
