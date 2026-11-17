import errno


class I2CDevice:
    def __init__(self, bus, lock, address):
        self.bus = bus
        self.lock = lock
        self.address = address

    def read(self, register, size):
        with self.lock:
            reply = self.bus.read_i2c_block_data(self.address, register, size)
        if len(reply) != size:
            raise OSError(errno.EIO, f"Short I2C read from 0x{self.address:02x}")
        return bytes(reply)

    def write(self, register, *values):
        with self.lock:
            self.bus.write_i2c_block_data(self.address, register, list(values))

    def command(self, command):
        with self.lock:
            self.bus.write_byte(self.address, command)

    def read_raw(self, size):
        from smbus2 import i2c_msg

        message = i2c_msg.read(self.address, size)
        with self.lock:
            self.bus.i2c_rdwr(message)
        return bytes(message)


def require_id(port, register, expected):
    chip_id = port.read(register, len(expected))
    if chip_id != expected:
        raise OSError(errno.ENODEV, f"Chip ID {chip_id.hex()} expected {expected.hex()}")
