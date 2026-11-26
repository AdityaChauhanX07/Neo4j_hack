# Simulated closed-loop recovery

`commoncause run --virtual-bench --auto-recover` can attempt an I2C bus
reinitialization after the graph identifies a single, high-confidence bus
fault. The controller reads the stored diagnosis and linked procedure. It
does not read the fault marker or expected answer to choose an action.

## Try the recoverable and persistent cases

```bash
commoncause run --virtual-bench --auto-recover --scenario sim/scenarios/bus-recovery.json --run recovery-demo --db board/recovery-store --recording board/recovery-demo.jsonl --tui
```

The scenario injects F2 and leaves it active. In the recoverable model, a
bus clear releases its latched failure, drivers initialize on their next
poll, and healthy readings resolve the diagnosis. The controller records
`verified` only after that resolution and fresh OK evidence on every
channel attached to the bus.

Use a new store and recording to exercise an ineffective action:

```bash
commoncause run --virtual-bench --auto-recover --persistent-bus-fault --scenario sim/scenarios/bus-recovery.json --run persistent-demo --db board/persistent-store --recording board/persistent-demo.jsonl --tui
```

Here the same action leaves the bus unavailable. After three seconds of
recorded verification time, the attempt becomes `not_recovered`; the
diagnosis stays open. There is one attempt per episode, so a persistent
fault cannot trigger an endless retry loop. Ending a capture before a
conclusive result records `unverified`.

Power faults, intermittent/uncertain diagnoses, UART faults, and multiple
suspects are left for inspection. The automatic path requires one bus
suspect, high confidence, zero healthy-device contradictions, a configured
I2C adapter, and the linked `bus-held-low` recovery procedure. A new fault
injection resets the virtual bus latch. Clearing a bus cannot restore a
failed supply or the combined F9 fault.

## Inspect the action history

Connect the [live browser](live-browser.md) to the capture store to see the
**Simulated recovery** table beside the diagnosis. A normal downlink export
retains the same table for later inspection:

```bash
commoncause downlink --db board/recovery-store --out board/recovery-downlink
```

`RecoveryAttempt` nodes contain the target, triggering frame timestamp,
procedure, simulated action, outcome, and finish time. `ATTEMPTED`, `TARGETS`,
and `USES` link the action to its diagnosis, bus, and catalogue procedure.
A verified attempt also has `VERIFIED_BY` pointing to a fresh OK event that
resolved the diagnosis. The browser console or read-only MCP can read them:

```cypher
MATCH (dx:Diagnosis)-[:ATTEMPTED]->(a:RecoveryAttempt)-[:TARGETS]->(b:Bus)
RETURN dx.id, b.id, a.action, a.state, a.ts, a.finished
```

Raw sensor JSONL replays the resulting diagnosis and observed recovery.
Action history is retained in the original store and exported downlink;
plain replay does not invent or re-execute those actions.

The feature is an opt-in simulation of policy, action, and verification.
`--auto-recover` refuses physical capture before opening a store. The
virtual action changes a register model; electrical SDA/SCL pulses, GPIO
control, and physical recovery are outside the project scope. Existing
manual virtual scenarios and the 36-injection benchmark keep their default
behavior when the flag is absent.

`tests/test_recovery.py` covers both I2C buses, persistent failure, refusal
of unsafe candidates, incomplete verification, reinjection, physical-mode
rejection, and replay of captured outcomes.
