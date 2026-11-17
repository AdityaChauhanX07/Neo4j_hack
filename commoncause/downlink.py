import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import relate


def graph_json(db):
    rows = db.execute("""
        MATCH (n)
        RETURN elementId(n) AS key, labels(n)[0] AS label, properties(n) AS props
    """).fetchall()
    keys = {
        row["key"]: f"{row['label']}:{row['props'].get('id', row['props'].get('code'))}"
        for row in rows
    }
    nodes = [
        {"id": keys[row["key"]], "label": row["label"], "props": row["props"]}
        for row in rows
    ]
    links = db.execute("""
        MATCH (a)-[r]->(b)
        RETURN type(r) AS type, elementId(a) AS source, elementId(b) AS target,
               properties(r) AS props
    """).fetchall()
    rels = [
        {"type": row["type"], "from": keys[row["source"]], "to": keys[row["target"]],
         "props": row["props"]}
        for row in links
    ]
    return {
        "nodes": sorted(nodes, key=lambda node: node["id"]),
        "rels": sorted(rels, key=lambda rel: (rel["from"], rel["type"], rel["to"])),
    }


def downlink(source, out, relate_cli="relate"):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out) as scratch:
        store = Path(scratch) / "common-cause.rl"
        export = store.with_suffix(".json")
        subprocess.run(
            [relate_cli, "clone", str(source), str(store)],
            check=True, text=True, capture_output=True,
        )
        with relate.connect(str(store), read_only=True) as db:
            export.write_text(json.dumps(graph_json(db), ensure_ascii=False) + "\n", encoding="utf-8")
        store.replace(out / store.name)
        export.replace(out / export.name)
