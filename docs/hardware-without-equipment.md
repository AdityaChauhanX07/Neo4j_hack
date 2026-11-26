# Exercising the bench without equipment

Research checked on November 26, 2026. The laptop setup, Python
compatibility checks, and varied fault simulations are covered in
[validation.md](validation.md). No physical bench is needed for that scope.

## Recommendation

Build an interactive virtual bench around the existing recorder and sensor
drivers. Replace the I2C and UART transports with explicit software models,
while keeping chip identification, register conversion, polling, heartbeat
decoding, diagnosis, and export on the existing code paths.

There is already a working test version in
[`test_live_session.py`](../tests/test_live_session.py): it supplies sensor
register responses and heartbeat bytes, types F1 through F5 on a
pseudo-terminal, and scores the recording from `commoncause run`. This is
software-in-the-loop testing. Turning it into an explicit user mode would
make the same exercise available outside pytest, without new equipment or
a hosted simulation subscription.

## Options assessed

The capabilities below come from the linked project documentation. The
fit and effort assessments are specific to Common Cause; these tools have
not been integrated into this repository.

| Option | What it offers | Fit for this project |
| --- | --- | --- |
| Local virtual bench | Our existing tests substitute register-level I2C responses and UART bytes while running the real drivers and recorder. | Recommended next step. Make transport injection explicit and expose interactive fault controls. |
| [Wokwi Pico](https://docs.wokwi.com/parts/wokwi-pi-pico) | RP2040 simulation with UART and I2C master support. The [component list](https://docs.wokwi.com/getting-started/supported-hardware) includes the MPU6050; the [custom chips API](https://docs.wokwi.com/chips-api/getting-started) can model other parts. | Useful for running the Pico heartbeat firmware. The supported board list does not include a Linux Pi 4, and several bench sensors need custom models. It does not replace the whole bench as supplied. |
| [QEMU Raspberry Pi](https://www.qemu.org/docs/master/system/arm/raspi.html) | The development manual lists `raspi4b`, serial ports, and a Broadcom I2C controller. | A possible later OS integration lane. Check the installed QEMU release and model the attached sensors before expecting the full workflow to run. The controller model alone does not supply our sensor behavior. |
| [Renode](https://renode.readthedocs.io/en/latest/basic/renode-testing-api.html) | Scriptable I2C targets and UART tests; [Python peripherals](https://renode.readthedocs.io/en/latest/basic/using-python.html) can enqueue register replies. | Useful if firmware or platform emulation becomes a priority. The exact bench platform and sensor models need a separate integration check. |
| [Linux i2c-stub](https://docs.kernel.org/i2c/i2c-stub.html) | A kernel module that answers SMBus operations from memory-backed registers without a physical chip. | Partial driver integration testing on a Linux machine with module-loading access. Our BH1750 path uses raw `i2c_rdwr`, so the documented SMBus operations do not establish compatibility with the whole bench. |

[Wokwi's pricing page](https://wokwi.com/pricing) currently lists a free
Community plan for public open-source projects. VS Code and CI features
are listed in paid tiers. The proposed local bench does not depend on
those paid features.

## Proposed next change

1. Add transport factories to the recorder and raw I2C path. Physical
   capture continues to use `smbus2` and `pyserial`; virtual capture selects
   software adapters explicitly. Avoid replacing imports globally as a
   production feature.
2. Reuse the test register models for the configured sensor chips. Model
   address failures, regulator voltage sag, bus loss, intermittent replies,
   and a 1 Hz heartbeat. Keep fault labels separate from diagnosis input.
3. Add an explicit virtual-bench CLI option. In that mode, the existing
   `F1 inject` and `F1 clear` commands change simulated device behavior and
   record markers. Show the existing live terminal view and write ordinary
   JSONL recordings.
4. Cover F1 through F9, including the delayed F5 reranking and both F9
   causes. Check healthy startup and recovery, then replay and score the
   captured bytes through the same matrix command.
5. Export the completed store and open its JSON in the existing ground
   view. Document one command sequence that works with laptop dependencies
   and no `/dev/i2c-*`, serial device, or administrator access.

Acceptance should require observed readings and graph evidence for every
verdict, reproducible recordings, no false diagnosis during healthy
operation, and recovery after clearing each modeled fault. A virtual run
must identify itself as simulated in its recording metadata and terminal
output.

## Further work after the virtual bench

Use independent scenario scripts to test delayed device failures, missing
telemetry, and ambiguous causes. Include cases that should remain uncertain
instead of expecting every scenario to achieve a perfect score. A separate
Wokwi Pico project is worthwhile if we want to execute the heartbeat
firmware itself rather than generate its serial protocol in Python.

Electrical properties still need physical evidence: supply isolation,
back-powering, pull-ups, current limits, actual chip variants, and measured
Pi performance. Models can encode assumptions about these effects, but
cannot confirm that real wiring meets them. Physical validation remains a
future extension, not a completion gate for the simulation project.
