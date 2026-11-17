from machine import Pin, UART
from time import sleep_ms

radio = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))
counter = 0

while True:
    radio.write(("CC1 %d\n" % counter).encode("ascii"))
    counter = (counter + 1) & 0xFFFFFFFF
    sleep_ms(1000)
