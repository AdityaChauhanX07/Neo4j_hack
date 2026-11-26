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
