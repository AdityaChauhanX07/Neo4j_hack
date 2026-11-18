# Common Cause

Draft text for the Devpost entry. Review the team details and add any
additional development tools used by teammates before submitting.

## Tagline

Trace shared sensor failures through power and data dependencies with embedded Relate.

## Inspiration

When several sensors stop responding, the failed devices can share a power
supply or data bus. Diagnosing each sensor separately misses those
relationships. Common Cause explores how a graph of the wiring and its
telemetry can help an operator find a shared cause.

## What it does

Common Cause ranks components that could explain an observed fault and
shows the evidence behind the ranking. Its ground view includes nine
simulated CubeSat faults and three simulated quadcopter faults. Viewers can
inspect the affected wiring, read the event timeline, run Cypher queries,
and download the simulated readings.

In CubeSat F1, a regulator dropout affects several devices and the diagnosis
points to `REG_B`. F2 changes the failure to a shared bus and identifies
`I2C-1`. F9 combines a regulator and bus fault, producing two ranked suspects.
The quadcopter cases use a different topology with the same diagnosis code.

## How it is built

Python loads a YAML topology into embedded Relate and replays JSONL
telemetry. The graph connects power rails, regulators, buses, drivers,
devices, channels, events, diagnoses, and recovery procedures. Cypher
traversals score a suspect by how many failed devices it explains and
how many healthy devices contradict it. When a suspect leaves failures
uncovered, the diagnosis can rank another cause for those devices.

The writable graph uses a Relate directory store. The repository includes
a persistent single-file F1 graph at `data/common-cause.rl` and a JSON
export at `downlink/common-cause.json`. The ground view reconstructs the
exported graph in embedded Relate WASM and executes queries locally in a
browser worker. Cytoscape.js renders the wiring. Shared topology and query
files keep replay and browser inspection consistent.

A read-only MCP configuration is included for inspecting the F1 graph from
a compatible client. The entry uses embedded Python for replay and WASM
for browser inspection, with Cypher queries in both environments.

## Technical challenges

A shared component may explain several failures but also supply healthy
devices. The ranking accounts for both observations. Combined faults need
another pass after the first suspect explains part of the failed devices.
Missing readings and stopped heartbeats also need timestamps and channel
cadence to distinguish a stale stream from a healthy one.

The project keeps the input recording, topology identity, and diagnosis
evidence together so a verdict can be inspected and reproduced.

## Results

| Simulated suite | Cases | Correct first suspect | First failed device baseline |
| --- | ---: | ---: | ---: |
| CubeSat | 9 | 9/9 | 2/9 |
| Quadcopter | 3 | 3/3 | 1/3 |

The baseline picks the first device that reports a failure. The matrix
command compares each prediction with the expected cause recorded in the
injection marker. F9 also recovers both expected causes in order.

These results cover deterministic simulated fixtures. Physical sensor
operation and performance on a Raspberry Pi remain unverified. The
optional recorder and drivers have automated tests using simulated I/O.

## What we learned

Healthy telemetry helps constrain a shared-cause diagnosis. Keeping the
wiring in a graph also allows the same queries to support a second topology
without adding another diagnosis implementation. Persisting the events
behind a verdict makes it possible to inspect the reasoning later.

## What's next

Broaden the simulated recordings with varied fault timing and recovery
patterns, then evaluate against those additional cases. Physical validation
can follow when a bench is available.

## Built with

Python, JavaScript, Relate, Cypher, WebAssembly, YAML, Cytoscape.js, Vite,
Geist, pytest, Playwright, and GitHub Actions. Python uses `relate-db` and
PyYAML. The optional board recorder uses smbus2 and pyserial. The browser
uses `@relate/relate-wasm`. The repository is licensed under Apache-2.0 and
the browser build includes third-party license files.

## AI tool use

ChatGPT assisted with implementation, debugging, automated tests, and
documentation. The running diagnosis uses the recorded telemetry,
topology, and Cypher ranking rules. The fixture scores are reproducible
from the checked-in simulator and matrix command.

## Links

- [Live ground view](https://adityachauhanx07.github.io/Neo4j_hack/)
- [Combined fault example](https://adityachauhanx07.github.io/Neo4j_hack/?case=cubesat%3AF9)
- [Repository and setup instructions](https://github.com/AdityaChauhanX07/Neo4j_hack)
- [Persistent Relate graph](https://github.com/AdityaChauhanX07/Neo4j_hack/blob/main/data/common-cause.rl)
- [90-second recording walkthrough](https://github.com/AdityaChauhanX07/Neo4j_hack/blob/main/docs/demo.md)

## Reproduce the scores

Follow the README's Python installation instructions, then run these
commands from the repository root.

```sh
python -m sim.demo
commoncause matrix ground/public/simulations/cubesat.jsonl
commoncause matrix ground/public/simulations/quadcopter.jsonl \
  --topology topologies/quadcopter.yaml
```
