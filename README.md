# Common Cause

Common Cause uses a Relate graph of a CubeSat bench to rank the parts that could
explain several sensor failures at once. Devices that still respond help rule
out shared power and data paths.

## How it uses Relate

The graph connects each device to its power supply and data bus. Telemetry
events connect to the device through its channels. The rank query walks those
relationships and scores each part by how many failed devices depend on it and
how many of its other devices still respond.

In the F1 fixture, losing power to `REG_B` silences three sensors across two
buses. `REG_B` covers all three, with no healthy devices downstream. `I2C-1`
covers only two, and two other devices on that bus still respond. The voltage
monitor reports undervoltage on `REG_B` and still counts as a responding device.

## Run the smoke test

Run these commands from the repository root with Python 3.9 or later.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[test]'
python -m pytest -q
```

The test builds the bench graph in memory and runs `queries/rank.cypher` against
fixture readings. It checks that `REG_B` ranks first with a score of 1.00, ahead
of the shared 5 V rail at 0.75 and `I2C-1` at 0.33. The query returns every
candidate so callers can choose how many to show.
