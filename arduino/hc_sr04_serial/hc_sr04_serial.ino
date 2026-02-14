// HC-SR04 -> Arduino -> Serial distance (cm)
// Wiring (Arduino Uno/Nano):
//   VCC  -> 5V
//   GND  -> GND
//   TRIG -> D9
//   ECHO -> D10
// Serial: 115200 baud, prints distance in cm (integer) per line.

const int PIN_TRIG = 9;
const int PIN_ECHO = 10;

const unsigned long PULSE_TIMEOUT_US = 30000; // ~5m max
const unsigned long MEASURE_INTERVAL_MS = 50; // 20 Hz

void setup() {
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  digitalWrite(PIN_TRIG, LOW);
  Serial.begin(115200);
}

unsigned long measure_cm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long duration = pulseIn(PIN_ECHO, HIGH, PULSE_TIMEOUT_US);
  if (duration == 0) {
    return 0; // timeout / out of range
  }
  // Speed of sound ~343 m/s => 58 us per cm (round trip)
  unsigned long cm = duration / 58;
  return cm;
}

void loop() {
  unsigned long cm = measure_cm();
  Serial.println(cm);
  delay(MEASURE_INTERVAL_MS);
}
