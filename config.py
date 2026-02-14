# config.py

import sys

# ===== Steering =====
STEERING_INVERT = True          # invert steering direction
STEERING_DEAD_ZONE = 0.03       # ignore small stick noise

SERVO_CENTER_US = 1600          # servo center pulse (µs)
SERVO_LEFT_US   = 950           # leftmost pulse (µs)
SERVO_RIGHT_US  = 2200          # rightmost pulse (µs)


# ===== Throttle =====
THROTTLE_INVERT = True          # invert throttle direction
THROTTLE_DEAD_ZONE = 0.05       # ignore small trigger noise

THROTTLE_NEUTRAL_US = 1600      # ESC neutral pulse (µs)
THROTTLE_FORWARD_US = 1900      # forward pulse (µs)
THROTTLE_REVERSE_US = 1100      # reverse pulse (µs)


# ===== Input =====
KEYBOARD_ENABLED = sys.stdin.isatty()  # only when TTY present
GAMEPAD_ENABLED = True                # enable DualShock input

GAMEPAD_DEVICE = "/dev/input/event5"  # DualShock device path

# Клавиши безопасности
KEYBOARD_ARM_KEY = "enter"
KEYBOARD_DISARM_KEY = "esc"

STEERING_GAIN = 1.8   # 1.5–2.5 обычно идеально

# ===== Auto cruise speed scaling =====
# Slow down when turning and/or when obstacles are close ahead.
AUTO_CRUISE_SPEED_DEFAULT = 0.25   # default auto speed (0..1)
AUTO_CRUISE_SPEED_MIN = 0.05       # minimum auto speed
AUTO_CRUISE_SPEED_MAX = 1.00       # maximum auto speed
AUTO_CRUISE_SPEED_STEP = 0.05      # step for +/- buttons

AUTO_TURN_STEER_THRESHOLD = 0.35   # slow down when steering above this
AUTO_TURN_SPEED_SCALE = 0.65       # speed scale when turning
AUTO_TURN_STEER_VALUE = 0.60       # auto-steer magnitude
AUTO_TURN_MANUAL_OVERRIDE = 0.15   # manual steer overrides auto
AUTO_TURN_RAMP_PER_SEC = 2.0       # auto-steer ramp speed (units/sec)

# Limit steering at higher speeds (AUTO only)
AUTO_STEER_SPEED_LOW = 0.10        # speed where steer limit starts
AUTO_STEER_SPEED_HIGH = 0.35       # speed where max limit reached
AUTO_STEER_MAX_LOW = 1.00          # max steer at low speed
AUTO_STEER_MAX_HIGH = 0.50         # max steer at high speed

AUTO_OBS_CENTER_THRESHOLD = 0.35   # slow down when center occupancy high
AUTO_CLOSEST_THRESHOLD = 0.75      # slow down when obstacle is close
AUTO_OBS_SPEED_SCALE = 0.50        # speed scale near obstacles

# ===== Vision snapshots =====
SNAPSHOT_ENABLED = True            # enable vision snapshots
SNAPSHOT_IMAGES = True             # save image with snapshot
SNAPSHOT_IMAGE_W = 320             # snapshot width (px)
SNAPSHOT_IMAGE_H = 240             # snapshot height (px)
SNAPSHOT_IMAGE_MAX_FPS = 5.0       # snapshot capture rate limit
SNAPSHOT_ON_STOP_DECISION = True   # snapshot on STOP/GO change
SNAPSHOT_ON_TURN_DECISION = False  # snapshot on turn change

# ===== Turn decision =====
TURN_CENTER_THRESHOLD = 0.35       # consider turn if center occupancy >= this
TURN_DIFF_THRESHOLD = 0.08         # side occupancy difference needed

# ===== Ultrasonic (Arduino) =====
US_ENABLED = True                  # use Arduino ultrasonic if available
US_SERIAL_PORT = "/dev/ttyACM0"    # Arduino serial port
US_BAUD = 115200                   # serial baud rate
US_SERIAL_TIMEOUT = 0.1            # serial read timeout (sec)
US_STOP_CM = 40.0                  # stop if <= this (cm)
US_GO_CM = 55.0                    # resume if >= this (cm)
US_EMA_ALPHA = 0.15                # smoothing factor (lower = smoother)
US_MIN_CM = 2.0                    # ignore closer than this
US_MAX_CM = 400.0                  # ignore farther than this
US_STALE_SEC = 1.2                 # data staleness timeout (sec)
US_DISPLAY_HOLD_SEC = 1.0          # keep last distance on display (sec)
US_CONTROL_HOLD_SEC = 0.5          # keep last valid distance for control (sec)

# ===== Version =====
APP_VERSION = "0.5.3"              # app version for logs/release notes

# ===== Camera history (for turn decision) =====
CAM_HISTORY_MAX_SEC = 3.0          # FIFO duration (sec)
CAM_HISTORY_TAU_SEC = 1.0          # exponential decay time constant (sec)
CAM_HISTORY_MIN_WEIGHT = 0.5       # minimum weight to use history
