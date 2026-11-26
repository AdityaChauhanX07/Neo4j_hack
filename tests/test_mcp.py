import hashlib
import io
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import relate

from commoncause.replay import replay
from commoncause.topology import load_topology
from sim.bench import records

ROOT = Path(__file__).resolve().parents[1]
CLI = os.environ.get("RELATE_CLI") or shutil.which("relate")
pytestmark = pytest.mark.skipif(not CLI, reason="Install the Relate CLI to check the MCP transport")


def exchange(store, calls):
    config = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]["commoncause"]
    args = list(config["args"])
    args[args.index("--database") + 1] = str(store)
    requests = [{
        "jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "commoncause-check", "version": "1"},
        },
    }, {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    requests.extend({"jsonrpc": "2.0", "id": index, **call}
                    for index, call in enumerate(calls, 1))
    session = subprocess.run(
        [CLI, *args], input="\n".join(map(json.dumps, requests)) + "\n",
        text=True, capture_output=True, timeout=20, cwd=ROOT,
    )
    assert session.returncode == 0, session.stderr
    replies = {reply["id"]: reply for reply in map(json.loads, session.stdout.splitlines())}
    assert replies[0]["result"]["serverInfo"]["name"] == "relate-mcp"
    assert len(replies) == len(calls) + 1
    return [replies[index] for index in range(1, len(calls) + 1)]


def call(name, **arguments):
    return {"method": "tools/call", "params": {"name": name, "arguments": arguments}}


def rows(reply):
    assert "error" not in reply, reply
    result = reply["result"]
    assert not result.get("isError"), result
    envelope = json.loads(result["content"][0]["text"])
    assert envelope["error"] is None
    return envelope["rows"]


def test_mcp_reads_linked_diagnosis_evidence_and_recovery_with_valid_citations(tmp_path):
    store = tmp_path / "fixture.rl"
    shutil.copyfile(ROOT / "data" / "common-cause.rl", store)
    recovery = (ROOT / "queries" / "recovery.cypher").read_text()
    replies = exchange(store, [
        {"method": "tools/list"},
        call("get_schema"),
        call("read_cypher", statement="""
            MATCH (dx:Diagnosis)-[s:SUSPECTS]->(c)
            RETURN dx.id AS diagnosis, dx.confidence AS confidence, dx.state AS state,
                   c.id AS suspect, s.covered AS covered, s.contradicted AS contradicted
            ORDER BY s.rank
        """),
        call("read_cypher", statement="""
            MATCH (:Diagnosis {id: $id})-[:BASED_ON]->(e:Event)-[:ON]->(ch:TelemetryChannel)
            RETURN e.id AS event, ch.id AS channel, e.status AS status
        """, parameters={"id": "dx:f1-fixture:1"}),
        call("read_cypher", statement=recovery, parameters={"id": "dx:f1-fixture:1"}),
        call("read_cypher", statement="MATCH (n) RETURN n.id AS id"),
    ])
    assert {tool["name"] for tool in replies[0]["result"]["tools"]} == {"get_schema", "read_cypher"}
    schema = json.loads(replies[1]["result"]["content"][0]["text"])
    assert {"Diagnosis", "Event", "Regulator", "RecoveryProcedure"} <= schema.keys()
    verdict, = rows(replies[2])
    assert verdict == {
        "diagnosis": "dx:f1-fixture:1", "confidence": "high", "state": "resolved",
        "suspect": "REG_B", "covered": 3, "contradicted": 0,
    }
    evidence = rows(replies[3])
    assert {row["status"] for row in evidence} == {"NO_RESPONSE", "UNDERVOLTAGE"}
    procedures = rows(replies[4])
    assert procedures and all(row["steps"] for row in procedures)
    citations = {verdict["diagnosis"], verdict["suspect"]}
    citations.update(value for row in evidence for value in (row["event"], row["channel"]))
    citations.update(value for row in procedures for value in (row["mode_id"], row["procedure_id"]))
    assert citations <= {row["id"] for row in rows(replies[5])}


def test_mcp_refuses_both_write_tools_and_mutations_disguised_as_reads(tmp_path):
    store = tmp_path / "fixture.rl"
    shutil.copyfile(ROOT / "data" / "common-cause.rl", store)
    before = hashlib.sha256(store.read_bytes()).hexdigest()
    attempts = [call("write_cypher", statement="CREATE (:Device {id: 'mcp-probe'})")]
    attempts.extend(call("read_cypher", statement=statement) for statement in (
        "CREATE (:Device {id: 'mcp-probe'})",
        "MATCH (n:Diagnosis) SET n.confidence = 'changed' RETURN n",
        "MATCH (n:Diagnosis) DETACH DELETE n",
        "CREATE INDEX mcp_probe FOR (n:Diagnosis) ON (n.confidence)",
    ))
    replies = exchange(store, attempts + [call("read_cypher", statement="MATCH (n) RETURN count(n) AS total")])
    for reply in replies[:-1]:
        assert "error" in reply or reply.get("result", {}).get("isError"), reply
    assert rows(replies[-1])[0]["total"] > 0
    assert hashlib.sha256(store.read_bytes()).hexdigest() == before


def test_mcp_preserves_medium_confidence_for_intermittent_evidence(tmp_path):
    store = tmp_path / "intermittent"
    with relate.connect(str(store)) as db:
        load_topology(db, ROOT / "topologies" / "cubesat-bench.yaml")
        replay(db, io.StringIO("\n".join(map(json.dumps, records("F8")))))
    reply, = exchange(store, [call("read_cypher", statement="""
        MATCH (dx:Diagnosis)-[:SUSPECTS]->(c)
        RETURN dx.confidence AS confidence, c.id AS suspect
    """)])
    assert rows(reply) == [{"confidence": "medium", "suspect": "sun2"}]
