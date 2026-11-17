import json
from pathlib import Path

import relate

from commoncause.downlink import graph_json
from commoncause.view import diagnosis

ROOT = Path(__file__).resolve().parents[1]


def test_fixture_snapshot_and_export_agree():
    export = json.loads((ROOT / "downlink" / "common-cause.json").read_text())
    with relate.connect(str(ROOT / "data" / "common-cause.rl"), read_only=True) as db:
        assert graph_json(db) == export
        verdict = diagnosis(db)
        assert verdict["state"] == "resolved"
        assert verdict["suspects"][0]["id"] == "REG_B"

    ids = {node["id"] for node in export["nodes"]}
    assert len(ids) == len(export["nodes"])
    assert all(link["from"] in ids and link["to"] in ids for link in export["rels"])
