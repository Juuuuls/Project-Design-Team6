#include "Ultrasonic.h"

// First sensor pair
int loudnessPin1 = A0;     // First loudness sensor input
Ultrasonic ultrasonic1(7); // First ultrasonic sensor (0° to 180°)

// Second sensor pair
int loudnessPin2 = A1;     // Second loudness sensor input
Ultrasonic ultrasonic2(3); // Second ultrasonic sensor (185° to 355°)

unsigned long lastMeasureTime = 0;
const unsigned long interval = 3500;  // 3.5 seconds between measurements for reliable data collection
bool firstSensorTurn = true;  // Toggle between sensors

void setup() {
  Serial.begin(9600);
  // No header needed - Python script handles headers
}

void loop() {
  unsigned long currentTime = millis();

  if (currentTime - lastMeasureTime >= interval) {
    lastMeasureTime = currentTime;

    // Alternate between sensors
    if (firstSensorTurn) {
      // --- First Sensor Pair (0° to 180°) ---
      measureAndReport(ultrasonic1, loudnessPin1, 1);
    } else {
      // --- Second Sensor Pair (185° to 355°) ---
      measureAndReport(ultrasonic2, loudnessPin2, 2);
    }

    firstSensorTurn = !firstSensorTurn;  // Toggle for next measurement
  }
}

void measureAndReport(Ultrasonic& sensor, int loudnessPin, int sensorNumber) {
    // --- Measure Ultrasonic Distance ---
    long distance = sensor.MeasureInCentimeters();

    // --- Measure Reverberation (Peak Time) ---
    unsigned long startTime = millis();
    int peakValue = -1;
    float peakTime = 0.0;

    while (millis() - startTime < 1000) {   // 1-second recording window
      int loudnessValue = analogRead(loudnessPin);

      unsigned long elapsed = millis() - startTime;
      float timeInSeconds = elapsed / 1000.0;

      if (loudnessValue > peakValue) {
        peakValue = loudnessValue;
        peakTime = timeInSeconds;
      }

      delay(5); // ~200 samples per second
    }

    // --- Output Sensor Number, Ultrasonic and RT60 ---
    Serial.print(sensorNumber);
    Serial.print(",");
    Serial.print(distance);
    Serial.print(",");
    Serial.println(peakTime, 3);
}