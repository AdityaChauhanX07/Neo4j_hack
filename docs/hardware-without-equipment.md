# Exercising the bench without equipment

Research checked on November 26, 2026. The laptop setup, Python
compatibility checks, and varied fault simulations are covered in
[validation.md](validation.md). No physical bench is needed for that scope.

## Recommendation

The [interactive virtual bench](virtual-bench.md) now implements this
approach. It replaces I2C and UART transports with explicit software models
and keeps chip identification, register conversion, polling, heartbeat
decoding, diagnosis, and export on the existing code paths.

The original test version is in
[`test_live_session.py`](../tests/test_live_session.py): it supplies sensor
register responses and heartbeat bytes, types F1 through F5 on a
pseudo-terminal, and scores the recording from `commoncause run`. This is
software-in-the-loop testing. The new `--virtual-bench` mode makes the
exercise available outside pytest, without new equipment or a hosted
simulation subscription.

## Options assessed

The capabilities below come from the linked project documentation. The
fit and effort assessments are specific to Common Cause. The local virtual
bench is implemented; the external emulators remain separate options.

| Option | What it offers | Fit for this project |
| --- | --- | --- |
| Local virtual bench | Explicit register-level I2C and UART transports run the real drivers and recorder. | Implemented with interactive and scripted F1 to F9 controls, recording, scoring, replay, and dashboard import. |
| [Wokwi Pico](https://docs.wokwi.com/parts/wokwi-pi-pico) | RP2040 simulation with UART and I2C master support. The [component list](https://docs.wokwi.com/getting-started/supported-hardware) includes the MPU6050; the [custom chips API](https://docs.wokwi.com/chips-api/getting-started) can model other parts. | Useful for running the Pico heartbeat firmware. The supported board list does not include a Linux Pi 4, and several bench sensors need custom models. It does not replace the whole bench as supplied. |
| [QEMU Raspberry Pi](https://www.qemu.org/docs/master/system/arm/raspi.html) | The development manual lists `raspi4b`, serial ports, and a Broadcom I2C controller. | A possible later OS integration lane. Check the installed QEMU release and model the attached sensors before expecting the full workflow to run. The controller model alone does not supply our sensor behavior. |
| [Renode](https://renode.readthedocs.io/en/latest/basic/renode-testing-api.html) | Scriptable I2C targets and UART tests; [Python peripherals](https://renode.readthedocs.io/en/latest/basic/using-python.html) can enqueue register replies. | Useful if firmware or platform emulation becomes a priority. The exact bench platform and sensor models need a separate integration check. |
| [Linux i2c-stub](https://docs.kernel.org/i2c/i2c-stub.html) | A kernel module that answers SMBus operations from memory-backed registers without a physical chip. | Partial driver integration testing on a Linux machine with module-loading access. Our BH1750 path uses raw `i2c_rdwr`, so the documented SMBus operations do not establish compatibility with the whole bench. |

[Wokwi's pricing page](https://wokwi.com/pricing) currently lists a free
Community plan for public open-source projects. VS Code and CI features
are listed in paid tiers. The proposed local bench does not depend on
those paid features.

## Implemented workflow

1. Transport factories in the recorder and raw I2C path. Physical
   capture continues to use `smbus2` and `pyserial`; virtual capture selects
   software adapters explicitly.
2. Register models for the configured sensor chips cover
   address failures, regulator voltage sag, bus loss, intermittent replies,
   and a 1 Hz heartbeat. Fault labels stay separate from diagnosis input.
3. The explicit virtual-bench CLI option makes the existing
   `F1 inject` and `F1 clear` commands change simulated device behavior and
   record markers. It supports the live terminal view and JSONL recordings.
4. Live tests cover F1 through F9, delayed F5 reranking, both F9 causes,
   healthy startup, and recovery. The matrix scores the captured bytes.
5. Replay and export retain the simulation flag. The existing ground view
   identifies imported virtual captures as simulated.

Acceptance requires observed readings and graph evidence for every
verdict, reproducible recordings, no false diagnosis during healthy
operation, and recovery after clearing each modeled fault. A virtual run
must identify itself as simulated in its recording metadata and terminal
output.

## Independent scenarios and firmware

Independent unlabelled scenarios now cover delayed device failures,
missing telemetry, and ambiguous causes. A diagnosis stays at medium
confidence when the power causes cannot yet be distinguished, then
refreshes when new healthy evidence arrives. Wokwi remains an optional
way to execute the Pico firmware rather than generate its protocol in
Python.

Electrical properties still need physical evidence: supply isolation,
back-powering, pull-ups, current limits, actual chip variants, and measured
Pi performance. Models can encode assumptions about these effects, but
cannot confirm that real wiring meets them. Physical validation remains a
future extension, not a completion gate for the simulation project.
