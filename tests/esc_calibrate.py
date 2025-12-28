import time
from hardware.throttle import Throttle

# ВАЖНО: channel тот, куда подключен сигнал ESC (у тебя 1)
t = Throttle(channel=1, neutral_us=1550, reverse_us=1100, forward_us=1900)

print("ESC CALIBRATION")
print("1) Сейчас отправлю FULL FORWARD (1900us) на 3 секунды. Включай питание ESC/аккум.")
t._set_us(1900)
time.sleep(3)

print("2) Сейчас отправлю FULL REVERSE (1100us) на 3 секунды.")
t._set_us(1100)
time.sleep(3)

print("3) Сейчас NEUTRAL (1550us).")
t._set_us(1550)
time.sleep(5)

print("Готово. Если ESC заармился — LED должен стать постоянным/сменить режим, мотор начать реагировать.")