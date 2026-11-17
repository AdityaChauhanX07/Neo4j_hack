from pathlib import Path

import pytest
import relate

from commoncause.topology import load_topology, read_channels

BENCH = Path(__file__).with_name("fixtures") / "cubesat-bench.yaml"


def test_load_topology_twice():
    with relate.connect() as db:
        load_topology(db, BENCH)
        counts = db.execute("MATCH ()-[r]->() RETURN count(r) AS links").fetchone()
        load_topology(db, BENCH)
        assert db.execute("MATCH ()-[r]->() RETURN count(r) AS links").fetchone() == counts
        channels = read_channels(db)
        assert len(channels) == 11
        assert channels["eps.regb.voltage"].monitor == "REG_B"
        assert channels["eps.regb.voltage"].device == "epsmon"


def test_invalid_wiring_leaves_store_empty(tmp_path):
    broken = tmp_path / "invalid.yaml"
    broken.write_text(BENCH.read_text().replace("powered_by: REG_B", "powered_by: missing"))
    with relate.connect() as db:
        with pytest.raises(ValueError, match="invalid POWERED_BY"):
            load_topology(db, broken)
        assert db.execute("MATCH (n) RETURN count(n) AS nodes").fetchone()["nodes"] == 0
