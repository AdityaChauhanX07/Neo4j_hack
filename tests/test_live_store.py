import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

import pytest
import relate

from commoncause.downlink import downlink, graph_json

ROOT = Path(__file__).resolve().parents[1]
CLI = os.environ.get("RELATE_CLI") or shutil.which("relate")
pytestmark = pytest.mark.skipif(not CLI, reason="Install the Relate CLI to check concurrent readers")


def test_clone_and_a_live_mcp_follower_coexist_with_the_recorder(tmp_path):
    store, recording = tmp_path / "store", tmp_path / "healthy.jsonl"
    replies = Queue()
    follower = None
    with (tmp_path / "capture.log").open("w") as capture_log, (tmp_path / "follower.log").open("w") as follower_log:
        writer = subprocess.Popen([
            sys.executable, "-c", "from commoncause.cli import main; raise SystemExit(main())",
            "run", "--virtual-bench", "--duration", "5", "--run", "concurrent",
            "--db", str(store), "--recording", str(recording),
        ], cwd=ROOT, stdout=capture_log, stderr=capture_log)
        try:
            deadline = time.monotonic() + 10
            while not recording.exists():
                assert writer.poll() is None, (tmp_path / "capture.log").read_text()
                assert time.monotonic() < deadline, "Recorder did not start"
                time.sleep(0.02)
            follower = subprocess.Popen([
                CLI, "serve", "--database", str(store), "--mcp", "stdio", "--read-only=live",
            ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=follower_log, text=True, bufsize=1)

            def receive():
                for line in follower.stdout:
                    replies.put(json.loads(line))

            reader = Thread(target=receive, daemon=True)
            reader.start()
            request_id = 0

            def request(method, params):
                nonlocal request_id
                request_id += 1
                follower.stdin.write(json.dumps({
                    "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
                }) + "\n")
                follower.stdin.flush()
                try:
                    reply = replies.get(timeout=10)
                except Empty:
                    pytest.fail("Live MCP reader did not answer: " + (tmp_path / "follower.log").read_text())
                assert reply["id"] == request_id and "error" not in reply, reply
                return reply["result"]

            def live_count():
                result = request("tools/call", {"name": "read_cypher", "arguments": {
                    "statement": "MATCH (e:Event) RETURN count(e) AS count",
                }})
                assert not result.get("isError"), result
                return json.loads(result["content"][0]["text"])["rows"][0]["count"]

            request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                   "clientInfo": {"name": "commoncause-live-check", "version": "1"}})
            first = live_count()
            while first == 0:
                assert time.monotonic() < deadline and writer.poll() is None
                time.sleep(0.02)
                first = live_count()
            assert writer.poll() is None
            downlink(store, tmp_path / "downlink", relate_cli=CLI)
            assert writer.poll() is None, "Capture ended before concurrent cloning was checked"
            snapshot = tmp_path / "downlink" / "common-cause.rl"
            exported = json.loads((tmp_path / "downlink" / "common-cause.json").read_text())
            with relate.connect(str(snapshot), read_only=True) as db:
                assert graph_json(db) == exported
                frozen = db.execute("MATCH (e:Event) RETURN count(e) AS count").fetchone()["count"]
            assert frozen >= first
            later = live_count()
            while later <= frozen:
                assert time.monotonic() < deadline and writer.poll() is None
                time.sleep(0.05)
                later = live_count()
            assert writer.wait(timeout=10) == 0, (tmp_path / "capture.log").read_text()
            assert live_count() >= later
            with relate.connect(str(snapshot), read_only=True) as db:
                assert graph_json(db) == exported
        finally:
            if writer.poll() is None:
                writer.terminate()
                writer.wait(timeout=10)
            if follower is not None:
                follower.stdin.close()
                follower.wait(timeout=10)
                reader.join(timeout=1)
                follower.stdout.close()
