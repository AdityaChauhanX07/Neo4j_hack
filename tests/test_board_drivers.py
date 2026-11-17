from struct import pack

import pytest

from commoncause.board.drivers import BH1750, BME280, HMC5883L, INA219, MPU6050, QMC5883L


class Registers:
    def __init__(self, replies):
        self.replies = replies
        self.writes = []

    def read(self, register, size):
        reply = self.replies[register]
        assert len(reply) == size
        return reply

    def write(self, register, *values):
        self.writes.append((register, *values))

    def command(self, command):
        self.writes.append((command,))

    def read_raw(self, size):
        assert len(self.replies[None]) == size
        return self.replies[None]


def test_mpu_ranges_and_signed_samples():
    port = Registers({0x75: b"\x68", 0x3B: pack(">7h", -8192, 0, 8192, 0, 131, -262, 393)})
    imu = MPU6050(port)
    imu.initialize()
    assert (0x1C, 0x08) in port.writes
    assert imu.read() == {"gyro": [1, -2, 3], "accel": [-1, 0, 1]}


@pytest.mark.parametrize(("driver", "registers", "field"), [
    (QMC5883L, {0x0D: b"\xff", 0x06: b"\x01", 0x00: pack("<3h", 120, -240, 360)}, [1, -2, 3]),
    (HMC5883L, {0x0A: b"H43", 0x03: pack(">3h", 109, 327, -218)}, [10, -20, 30]),
])
def test_magnetometer_axis_order_and_units(driver, registers, field):
    sensor = driver(Registers(registers))
    sensor.initialize()
    assert sensor.read()["field"] == pytest.approx(field)


def test_ina219_uses_signed_shunt_and_bus_registers():
    monitor = INA219(Registers({0x01: pack(">h", -100), 0x02: pack(">H", (825 << 3) | 2)}), 0.1)
    monitor.initialize()
    assert monitor.read() == pytest.approx({"voltage": 3.3, "current": -10})


def test_bme280_compensated_reading():
    calibration = [27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000]
    raw = (415148 << 4).to_bytes(3, "big") + (519888 << 4).to_bytes(3, "big")
    sensor = BME280(Registers({0xD0: b"\x60", 0xF3: b"\x00", 0x88: pack("<HhhH8h", *calibration), 0xF7: raw}))
    sensor.initialize()
    assert sensor.read() == pytest.approx({"temperature": 25.082, "pressure": 1006.533}, abs=0.003)


def test_bh1750_uses_raw_read_after_power_on():
    port = Registers({None: pack(">H", 120)})
    sensor = BH1750(port)
    sensor.initialize()
    assert port.writes == [(0x01,), (0x10,)]
    assert sensor.read() == {"lux": 100}
