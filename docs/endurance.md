# Virtual endurance measurement

Run from the repository root on Linux or macOS with the Python package
installed. `resource.getrusage` supplies peak RSS, so this runner does not
support Windows. It uses the actual recorder and Relate writer with the
virtual sensor transports, without board packages.

```sh
python -m scripts.soak --duration 3600 --out board/endurance-hour
```

Use a new output directory. The runner keeps raw `healthy.jsonl`, the
writable `store`, one-minute `progress.json` checkpoints, and `report.json`.
It exits unsuccessfully if any diagnosis appears, any channel is unhealthy,
or cadence falls below 90% of that channel's configured rate. The span
allows one second for startup and shutdown. Sensors are sampled at 2 Hz;
the radio heartbeat is 1 Hz.

The report records the platform, interpreter, source revision, runner and
topology hashes, elapsed time, event count, recording hash, store bytes,
and peak RSS during acquisition. Memory includes Python, the simulated
transports, the Relate graph, and the recorder's threads in this process.
Store bytes describe the live directory, not a compact `.rl` snapshot.

An uninterrupted one-hour healthy run also supplies the planned ten-minute
healthy recording. Keep the full input for replay and inspect the per-channel
health report. These are measurements on the machine running the model;
they do not establish Pi resource use or electrical behavior.

The **Virtual endurance** workflow offers the same check through **Run
workflow**, defaulting to 3,600 seconds, and saves the complete output as
the `virtual-endurance` artifact. Pull requests that change the runner use
a five-second smoke run; that is not an endurance result.

## November 26 measurement

An uninterrupted run on x64 Linux with Python 3.11.18 completed with no
diagnosis and healthy input on every channel. Sensors measured 2.00 Hz;
the radio measured 1.00 Hz.

| Measurement | Result |
| --- | ---: |
| Requested live duration | 3,600 seconds |
| Measured process duration | 3,600.445 seconds |
| Recorded telemetry span | 3,599.504 seconds |
| Diagnoses during healthy operation | 0 |
| Persisted events | 33,772 |
| Peak acquisition RSS | 116,236,288 bytes (110.85 MiB) |
| Closed directory store | 1,615,808 bytes (1.54 MiB) |
| Largest minute store checkpoint | 3,831,629 bytes |
| Raw recording | 10,539,384 bytes |
| Compressed hour recording | 476,757 bytes |

The [full report](endurance-results.json) retains every minute checkpoint,
per-channel counts, maximum gaps, platform, source revision, and hashes.
The run measured production code at `73be4a8` with the runner identified by
its recorded SHA-256. It predates the later atomic-verdict fix; the healthy
defaults and topology used here are unchanged. Current tests reclassify
the retained input. The final fault matrix is a separate measurement of
the updated ingestion code.

The [manifest](endurance-manifest.json) identifies the compressed hour
recording and a 601-second prefix that satisfies the original ten-minute
healthy-capture gate. The [prefix report](ten-minute-health.json) keeps its
own cadence checks and raw hash. These files remain in git after CI
artifacts expire.

To inspect the hour input without running another hour:

```sh
python -c "import gzip; from pathlib import Path; p=Path('board/healthy-hour.jsonl'); p.parent.mkdir(exist_ok=True); p.write_bytes(gzip.decompress(Path('recordings/virtual-healthy-hour.jsonl.gz').read_bytes()))"
commoncause check-capture board/healthy-hour.jsonl --min-seconds 3599 --min-rate 0.9
```

This rechecks recorded cadence and classifications. A new live duration
and resource measurement uses the runner command at the top of this page.
The minute store figures include WAL/checkpoint churn; they are sampled
sizes, while peak RSS is the operating system's process high-water mark.
