# Original plan and current scope

This reconciles the November 16 plan with the agreed laptop/browser scope.
The team has no bench equipment. Physical validation remains a future
extension; simulated results are labelled throughout the application and
reports.

## Engineering deliverables

| Original requirement | Current evidence |
| --- | --- |
| Public repository, licence, topics, packaging, CI | Public repository with Apache-2.0, both hackathon topics, non-editable install checks, and passing Linux/Mac/Windows lanes |
| Frozen topology, telemetry, export, and query interfaces | YAML topology and hardware maps, JSONL recordings, JSON downlinks, and shared query files |
| Hand-built graph kill test | `tests/bench.cypher` and `test_regulator_input_loss` independently establish `REG_B` as the top candidate |
| Schema, constraints, idempotent loaders, failure catalogue | Loader tests, both topologies, and linked failure/recovery procedures |
| Classification, episodes, deterministic ranking | Unit/replay tests, independent Python ranking specification, unlabelled uncertainty cases, and shared detection config |
| CLI, live view, recorder, sensor drivers, heartbeat | Implemented; laptop virtual transports exercise the actual driver and acquisition paths |
| Replay, fault matrix, naive baseline | F1–F9, both F9 causes, recovery, first-correct timing, and bounded seeded trials |
| Downlink while the daemon runs | A separate live MCP follower sees new commits while cloning produces an unchanged `.rl`/JSON pair |
| Ground agent | Read-only MCP configuration, operator instructions, real protocol sessions, valid citation checks, and a checked explanation example |
| Browser ground view | Shared Cypher in Relate WASM, wiring paths, timeline, healthy contradictions, procedures, file import, query console, and recorded-session inspection |
| Second system | Quadcopter topology and three labelled synthetic faults using the same engine and queries |
| Clean Ubuntu and Mac setup | Fresh installed-package workflows on Linux and macOS; Windows coverage added as well |
| Final 36-injection matrix and inspectable store | Four live virtual repetitions of F1–F9, raw JSONL, persistent snapshot, JSON export, scores, benchmarks, and hash manifest |
| Ten-minute healthy recording and one-hour resource check | Real-clock virtual endurance runner, cadence/false-alarm checks, minute checkpoints, and retained recordings/reports |

The [validation notes](validation.md) identify the measured versions,
inputs, results, and limitations. The [recorded matrix](virtual-matrix.md)
and [endurance guide](endurance.md) provide the reproducible inputs and
commands. Core code, fixtures, and the completed one-hour measurement
cover the agreed software scope. Each measurement identifies its actual
source revision and host.

## Physical promises that remain unverified

Original tracker rows 1, 6, 8, and the physical portions of 10, 14, and 19
cover ordering equipment, Pi setup, wiring/isolation, physical capture,
and hardware fault runs. Scripts, drivers, maps, and checklists exist, but
they do not establish those physical results.

The original under-two-second Pi verdict target and Pi query/RSS figures
are unmeasured. The simulated F5 case needs heartbeat-loss evidence after
its initial regulator verdict, so a blanket under-two-second first-correct
claim would also misdescribe the current model.

Gate 2 should read **all sensor channels at 2 Hz, with the radio heartbeat
at 1 Hz**. The supplied topology, capture checker, tests, and bring-up guide
use that per-channel cadence. The hardware-free equivalent of the gate is
a healthy ten-minute virtual capture, rather than a claim of Pi operation.

The Pico firmware is supplied and checked with a MicroPython test double.
Actual RP2040 emulator execution remains optional and unverified; the
virtual UART generates its byte protocol in Python.

## Optional original stretch goals

- Pico-controlled MOSFET fault switches: physical extension; scripted
  virtual injection is already available.
- Automatic electrical recovery or I2C bus clear: deferred. The application
  records recovery evidence and displays the catalogue's operator guidance.
- PerovSat's real topology: conditional on access and permission; the
  quadcopter already demonstrates a second system.
- Live browser HTTP connection: deferred. The browser currently inspects
  frozen downlinks; live directory inspection works through CLI/MCP.

Submission copy, market rechecks, the video, rehearsal, and Devpost
publication are separate from this engineering checklist.
