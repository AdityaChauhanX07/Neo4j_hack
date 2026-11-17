from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

NODE_KEYS = {
    "Topology": "id",
    "PowerRail": "id",
    "Regulator": "id",
    "Bus": "id",
    "Device": "id",
    "Driver": "id",
    "TelemetryChannel": "id",
    "Event": "id",
    "Symptom": "code",
    "FailureMode": "id",
    "RecoveryProcedure": "id",
    "Diagnosis": "id",
    "Run": "id",
}


def install_schema(db):
    for label, key in NODE_KEYS.items():
        db.execute(
            f"CREATE CONSTRAINT {label.lower()}_{key} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
        )
    db.execute("CREATE INDEX event_ts IF NOT EXISTS FOR (e:Event) ON (e.ts)")
    db.execute("CREATE INDEX event_status IF NOT EXISTS FOR (e:Event) ON (e.status)")


def read_asset(folder, name):
    packaged = files("commoncause").joinpath(folder).joinpath(name)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    checkout = Path(__file__).resolve().parents[1] / folder / name
    return checkout.read_text(encoding="utf-8")


@contextmanager
def transaction(db):
    db.autocommit = False
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.autocommit = True


def merge_nodes(db, label, rows):
    key = NODE_KEYS[label]
    db.execute(
        f"UNWIND $rows AS row MERGE (n:{label} {{{key}: row.{key}}}) SET n += row",
        {"rows": rows},
    )


def merge_links(db, source, relationship, target, pairs):
    source_key, target_key = NODE_KEYS[source], NODE_KEYS[target]
    db.execute(
        f"UNWIND $pairs AS pair "
        f"MATCH (a:{source} {{{source_key}: pair[0]}}), "
        f"(b:{target} {{{target_key}: pair[1]}}) "
        f"MERGE (a)-[:{relationship}]->(b)",
        {"pairs": pairs},
    )
