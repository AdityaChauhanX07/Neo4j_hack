from math import ceil
from platform import machine
from time import perf_counter_ns

from .diagnose import RANK, rank_params


def percentiles(samples):
    ordered = sorted(samples)
    count = len(ordered)
    return {
        "samples": count,
        "p50": ordered[ceil(count * 0.50) - 1] if count else None,
        "p95": ordered[ceil(count * 0.95) - 1] if count else None,
    }


def benchmark(db, path, diagnosis_id=None, samples=100):
    if samples <= 0:
        raise ValueError("Benchmark samples must be positive")
    window = db.execute("""
        MATCH (dx:Diagnosis)
        WHERE $id IS NULL OR dx.id = $id
        RETURN dx.id AS id, dx.run AS run, dx.window_from AS start, dx.window_to AS stop
        ORDER BY dx.ts DESC, dx.id DESC
        LIMIT 1
    """, {"id": diagnosis_id}).fetchone()
    if not window:
        raise ValueError("No matching diagnosis to benchmark")

    params = rank_params(window["run"], window["start"], window["stop"])
    db.execute(RANK, params).fetchall()
    durations = []
    for _ in range(samples):
        start = perf_counter_ns()
        db.execute(RANK, params).fetchall()
        durations.append((perf_counter_ns() - start) / 1_000_000)
    size = path.stat().st_size if path.is_file() else sum(
        item.stat().st_size for item in path.rglob("*") if item.is_file()
    )
    commits = db.execute("""
        MATCH (dx:Diagnosis {run: $run})
        WHERE dx.first_commit_ts IS NOT NULL
        RETURN dx.first_commit_ts - dx.window_from AS elapsed
    """, {"run": window["run"]})
    return {
        "diagnosis": window["id"], "run": window["run"], "architecture": machine(),
        "rank_ms": percentiles(durations), "store_bytes": size,
        "live_verdict_ms": percentiles(row["elapsed"] for row in commits),
    }
