# Release Notes

## 0.5.5 - 2026-02-15
- Added ultrasonic serial auto-reconnect loop after startup failures/disconnects.
- Added ultrasonic STOP/GO frame debouncing.
- Added progressive speed reduction in 70..40 cm range before hard STOP.
- Reduced control hold window for stale ultrasonic data.

## 0.5.4 - 2026-02-14
- Camera no longer affects speed while ultrasonic is present.
- Camera is used only for turning and as fallback when ultrasonic device is absent.
- Added fail-safe stop state when ultrasonic device is present but data is invalid.

## 0.5.3 - 2026-02-14
- Improved Arduino serial parsing/initialization for ultrasonic stability.
- Added configurable ultrasonic serial timeout.
- Trimmed OLED vertical separator to avoid crossing bottom metrics.

## 0.5.2 - 2026-02-14
- Increased auto cruise speed range and step (up to 100%).

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
