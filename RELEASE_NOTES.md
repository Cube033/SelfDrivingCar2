# Release Notes

## 0.5.1 - 2026-02-14
- Added comments and tuned ultrasonic debounce settings.

## 0.5.0 - 2026-02-14
- Added Arduino HC-SR04 serial integration for forward stop decisions.
- Added camera FIFO history with weighted turn decisioning.
- Added OLED distance display and boot/shutdown messages.
- Added safe shutdown on gamepad Share button.
- Added vision snapshot capture with event metadata and reduced overhead.
- Display now updates without vision; shows vision error explicitly.
- Fixed vision stats crash and display init ordering.

## 0.4.0 - 2026-02-08
- Added weighted obstacle logic and closest-row detection.
- Added L/C/R occupancy bars and improved OLED layout.
- Added auto turn steering with ramp and speed limiting.
- Added snapshot logging for stop/turn events.
