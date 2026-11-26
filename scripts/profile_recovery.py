import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import relate

from scripts.profile_modes import WORKER


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Measure verified and ineffective virtual recovery attempts")
    parser.add_argument("--source", type=Path, required=True, help="checkout containing the backend to measure")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("This resource runner uses Linux RSS units")
    source, out = args.source.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "platform": platform.platform(), "python": platform.python_version(), "runs": [],
    }
    for repeat in range(1, 4):
        for persistent in (False, True):
            outcome = "not_recovered" if persistent else "verified"
            trial = out / f"{repeat}-{outcome}"
            trial.mkdir()
            store, recording = trial / "store", trial / "capture.jsonl"
            command = [sys.executable, "-c", WORKER, str(trial / "writer.json"), "run", "--virtual-bench",
                       "--auto-recover", "--scenario", "sim/scenarios/bus-recovery.json", "--run", "recovery-profile",
                       "--db", str(store), "--recording", str(recording)]
            if persistent:
                command.append("--persistent-bus-fault")
            with (trial / "capture.log").open("w") as log:
                subprocess.run(command, cwd=source, stdout=log, stderr=log, check=True, timeout=30)
            with relate.connect(str(store), read_only=True) as db:
                attempts = db.execute("""
                    MATCH (dx:Diagnosis)-[:ATTEMPTED]->(a:RecoveryAttempt)
                    RETURN a.state AS outcome, a.target AS target, dx.confidence AS confidence,
                           a.ts - dx.window_from AS attempt_from_first_bad_ms,
                           a.finished - a.ts AS verification_ms, dx.state AS diagnosis
                """).fetchall()
            if len(attempts) != 1 or attempts[0]["outcome"] != outcome:
                raise RuntimeError(f"Unexpected recovery outcome: {attempts}")
            result = {**json.loads((trial / "writer.json").read_text()), **attempts[0],
                      "trial": trial.name, "recording_sha256": hashlib.sha256(recording.read_bytes()).hexdigest()}
            report["runs"].append(result)
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(result), flush=True)
