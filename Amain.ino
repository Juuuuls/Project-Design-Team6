#include "Ultrasonic.h"

int loudnessPin = A0;     // Loudness sensor input
Ultrasonic ultrasonic(7); // Ultrasonic sensor (single-pin type)

unsigned long lastMeasureTime = 0;
const unsigned long interval = 2000;  // 3 seconds between measurements

void setup() {
  Serial.begin(9600);
  // Optional: label line for clarity or CSV header
}

void loop() {
  unsigned long currentTime = millis();

  if (currentTime - lastMeasureTime >= interval) {
    lastMeasureTime = currentTime;

    // --- Measure Ultrasonic Distance ---
    long distance = ultrasonic.MeasureInCentimeters();

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

    // --- Output both Ultrasonic and RT60 ---
    Serial.print(distance);
    Serial.print(",");
    Serial.println(peakTime, 3);
  }
}
