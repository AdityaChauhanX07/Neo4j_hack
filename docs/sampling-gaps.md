# Sampling gaps and component attribution

The retained hour at `0dcf7e9` opened three component diagnoses without an
injected fault. Its input contained real timing gaps: all returned values
were nominal, but several readings arrived after their deadlines.
That recording and its original failed report remain unchanged.

The old engine backdated each inferred gap to the missed deadline and
immediately used it as fault evidence. A sufficiently late observation
could therefore appear settled on arrival. It could also write an episode
after delayed healthy readings had already returned. The resulting
component suspect did not distinguish delayed acquisition from a fault.

## Current policy

Missing-reading detection and component attribution now remain separate:

1. Record the gap at its original missed deadline and retain its graph links.
2. Record when it was actually observed. Initially it is not diagnostic evidence.
3. Process new readings before evaluating pending confirmation.
4. Promote a gap only if the channel remains missing for the configured
   settle interval after observation. A reading on the confirmation boundary
   can clear it first.
5. Exclude unconfirmed gaps, and confirmations after a query's cutoff, from
   component ranking and healthy-device contradictions.

No sample timeout was relaxed. The capture checker still reports the same
unhealthy timing. A confirmation establishes persistent missing telemetry,
not a proven electrical cause; the ranked part remains an inference from
the graph and available observations.

The [configuration guide](detection.md) documents `diagnostic`, `observed_ts`,
and `confirmed_ts` on new events. The evidence workspace reports the Run's
missing-reading count, including recordings with no component diagnosis.
An unconfirmed gap inside an episode is marked separately in the timeline.

## Regression coverage

The complete [retained hour](final-endurance-manifest.json) now replays to
zero component diagnoses while preserving all 19 `STALE` events as
non-diagnostic missing-reading evidence. Its cadence check remains unhealthy.
This is a new replay of existing input, not a newly acquired clean hour.

Focused tests cover a global pause followed by healthy readings, a driver
that remains missing after other telemetry resumes, a reading on the
confirmation boundary, an explicit read error after a pause, and a timing
gap during another component fault. The independent rank specification and
WASM tests also check that future confirmation cannot leak into an earlier
query window. The browser imports a real exported gap-only graph and must
show a quality notice without a component diagnosis.

All 36 complete cause sets remain correct when replaying the retained
fault matrix. First-correct p50 is 1,001 ms and p95 is 3,503 ms on that
input; the four F5 trials take 2,505, 2,506, 3,503, and 4,000 ms. These are
recorded-time replay results under the new policy. The original capture's
published timing remains a historical measurement of its recorded source.

Waiting for observed absence can increase heartbeat/driver verdict time.
For the deterministic F5 fixture, the first regulator verdict is still
1,000 ms after the first anomaly, but the fully correct upstream rail
verdict now takes 3,500 ms. A first verdict and a first correct verdict
continue to be reported separately.

Older exported graphs remain compatible with the shared query parameters
and returned columns. They do not acquire confirmation metadata
retroactively. Replay their raw JSONL to get the new interpretation.
