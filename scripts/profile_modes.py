import argparse
import hashlib
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import urlopen

import relate

from commoncause.check_capture import check_capture

ROOT = Path(__file__).resolve().parents[1]
WORKER = """
import json, resource, sys
from pathlib import Path
from time import monotonic
from commoncause.cli import main
report = Path(sys.argv.pop(1))
started = monotonic()
exit_code = main()
usage = resource.getrusage(resource.RUSAGE_SELF)
report.write_text(json.dumps({'exit_code': exit_code, 'elapsed_seconds': monotonic() - started,
    'cpu_seconds': usage.ru_utime + usage.ru_stime, 'peak_rss_bytes': usage.ru_maxrss * 1024}) + '\\n')
raise SystemExit(exit_code)
"""


def follower_usage(pid):
    status = Path(f"/proc/{pid}/status").read_text()
    high = next(int(line.split()[1]) * 1024 for line in status.splitlines() if line.startswith("VmHWM:"))
    ticks = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {"peak_rss_bytes": high,
            "cpu_seconds": (int(ticks[11]) + int(ticks[12])) / os.sysconf("SC_CLK_TCK")}


def measure(out, seconds, mode, cli):
    out.mkdir(parents=True)
    store, recording = out / "store", out / "healthy.jsonl"
    live = mode in {"live", "combined"}
    recovery = mode in {"recovery", "combined"}
    args = [sys.executable, "-c", WORKER, str(out / "writer.json"), "run", "--virtual-bench",
            "--duration", str(seconds), "--run", "profile-healthy", "--db", str(store),
            "--recording", str(recording)]
    if recovery:
        args.append("--auto-recover")
    server = poller = None
    server_usage = None
    with (out / "writer.log").open("w") as writer_log, (out / "reader.log").open("w") as reader_log:
        writer = subprocess.Popen(args, cwd=ROOT, stdout=writer_log, stderr=writer_log)
        try:
            deadline = monotonic() + 20
            while not recording.exists():
                if writer.poll() is not None or monotonic() > deadline:
                    raise RuntimeError(f"Capture did not start: {out / 'writer.log'}")
                sleep(0.05)
            if live:
                with socket.socket() as available:
                    available.bind(("127.0.0.1", 0))
                    port = available.getsockname()[1]
                address = f"http://127.0.0.1:{port}"
                environment = {**os.environ, "RELATE_AUTH": "relate:" + secrets.token_hex(24)}
                server = subprocess.Popen([cli, "serve", "--database", str(store), "--http", str(port),
                                           "--read-only=live"], env=environment, stdout=reader_log, stderr=reader_log)
                while True:
                    try:
                        with urlopen(address, timeout=1) as response:
                            if response.status == 200:
                                break
                    except URLError:
                        if server.poll() is not None or monotonic() > deadline:
                            raise RuntimeError(f"HTTP follower did not start: {out / 'reader.log'}")
                        sleep(0.05)
                poller = subprocess.Popen(["node", str(ROOT / "scripts/poll-live.mjs"), address,
                                           str(out / "poller.json")], env=environment, stdout=reader_log, stderr=reader_log)
            writer.wait(timeout=seconds + 30)
            if writer.returncode:
                raise RuntimeError(f"Capture failed: {out / 'writer.log'}")
            if live:
                if poller.poll() is not None or server.poll() is not None:
                    raise RuntimeError(f"Live reader stopped early: {out / 'reader.log'}")
                poller.terminate()
                poller.wait(timeout=10)
                server_usage = follower_usage(server.pid)
        finally:
            for process in (poller, server, writer):
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
    result = json.loads((out / "writer.json").read_text())
    result.update(mode=mode, requested_seconds=seconds)
    if live:
        result["follower"] = server_usage
        result["poller"] = json.loads((out / "poller.json").read_text())
        if result["poller"]["failed"] or result["poller"]["polls"] < seconds * 0.8:
            raise RuntimeError(f"Live workload was incomplete: {out / 'poller.json'}")
    with recording.open() as feed:
        health = check_capture(feed, ROOT / "topologies/cubesat-bench.yaml", min_seconds=seconds - 1, min_rate=0.9)
    with relate.connect(str(store), read_only=True) as db:
        result["diagnoses"] = db.execute("MATCH (d:Diagnosis) RETURN count(d) AS n").fetchone()["n"]
    result["healthy"] = health["healthy"] and result["diagnoses"] == 0
    result["store_bytes"] = sum(p.stat().st_size for p in store.rglob("*") if p.is_file())
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "health.json").write_text(json.dumps(health, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare healthy acquisition with live reading and recovery policy enabled")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--relate", default="relate")
    args = parser.parse_args()
    if platform.system() != "Linux" or args.duration < 10:
        parser.error("Use Linux and a duration of at least 10 seconds")
    args.out.mkdir(parents=True, exist_ok=False)
    report = {
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "platform": platform.platform(), "python": platform.python_version(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "poller_sha256": hashlib.sha256((ROOT / "scripts/poll-live.mjs").read_bytes()).hexdigest(),
        "live_workload": "Healthy-view startup and 1 Hz read-query polling through the real HTTP client; browser rendering excluded",
        "runs": [],
    }
    for index, mode in enumerate(["baseline", "live", "recovery", "combined", "combined", "recovery", "live", "baseline"], 1):
        result = measure(args.out / f"{index}-{mode}", args.duration, mode, args.relate)
        report["runs"].append(result)
        report["passed"] = all(run["healthy"] for run in report["runs"])
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    raise SystemExit(0 if report["passed"] else 1)
