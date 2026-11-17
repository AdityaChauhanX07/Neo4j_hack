from .bh1750 import BH1750
from .bme280 import BME280
from .ina219 import INA219
from .magnetometer import HMC5883L, QMC5883L
from .mpu6050 import MPU6050

I2C_DRIVERS = {
    "bh1750": BH1750,
    "bme280": BME280,
    "hmc5883l": HMC5883L,
    "ina219": INA219,
    "mpu6050": MPU6050,
    "qmc5883l": QMC5883L,
}
