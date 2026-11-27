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
4. Require the channel to remain missing through the normal settling window.
   After whole-stream silence beyond the shortest channel timeout, restart
   confirmation from resumption rather than counting unobserved time.
5. Allow heartbeat loss to update a settled power diagnosis when fresh
   undervoltage evidence shares its upstream rail. An unrelated rail does
   not corroborate it. This also waits after whole-stream resumption.
6. Exclude unconfirmed gaps, and confirmations after a query's cutoff, from
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

The [replay report](sampling-gap-replay-results.json) pins the tested fix
source and retained inputs, with the current matrix scores and timings.

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

All 36 complete cause sets and recoveries remain correct when replaying the
retained fault matrix. The replay report contains the final timings and
identifies its exact measured source. Original capture results remain
historical measurements of their recorded source.

An initial version always waited a full interval after noticing a timeout.
CI exposed a short UART-loss trial and a live upstream rail fault that
recovered before that extra interval ended. The final policy preserves the
normal settling window during active acquisition and requires renewed
observation after whole-stream silence. All three varied seeds now run
four repetitions in the unit suite, matching the four-repeat CI workload.
The four-second live F5 test keeps its original hold duration.

For the deterministic F5 fixture, the first regulator verdict still takes
1,000 ms and the fully correct upstream rail verdict takes 2,500 ms after
the first anomaly. The shared voltage/heartbeat evidence permits that
update. A first verdict and a first correct verdict remain separate metrics.

Older exported graphs remain compatible with the shared query parameters
and returned columns. They do not acquire confirmation metadata
retroactively. Replay their raw JSONL to get the new interpretation.
