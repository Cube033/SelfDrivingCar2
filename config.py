# config.py

import sys

# ===== Steering =====
STEERING_INVERT = True
STEERING_DEAD_ZONE = 0.03

SERVO_CENTER_US = 1600
SERVO_LEFT_US   = 950
SERVO_RIGHT_US  = 2200


# ===== Throttle =====
THROTTLE_INVERT = True        
THROTTLE_DEAD_ZONE = 0.05

THROTTLE_NEUTRAL_US = 1600
THROTTLE_FORWARD_US = 1900
THROTTLE_REVERSE_US = 1100


# ===== Input =====
KEYBOARD_ENABLED = sys.stdin.isatty()
GAMEPAD_ENABLED = True

GAMEPAD_DEVICE = "/dev/input/event5"  # DualShock 4

# Клавиши безопасности
KEYBOARD_ARM_KEY = "enter"
KEYBOARD_DISARM_KEY = "esc"

STEERING_GAIN = 1.8   # 1.5–2.5 обычно идеально