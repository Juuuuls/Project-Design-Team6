int loudnessPin = A0;     // Loudness sensor input
unsigned long lastMeasureTime = 0;
const unsigned long interval = 3000;  // Measure every 3 seconds

void setup() {
  Serial.begin(9600);
  // Optional: label for CSV compatibility
  Serial.println("Reverberation(s)");
}

void loop() {
  unsigned long currentTime = millis();

  if (currentTime - lastMeasureTime >= interval) {
    lastMeasureTime = currentTime;

    // Record for 1 second
    unsigned long startTime = millis();
    int peakValue = -1;
    float peakTime = 0.0;

    while (millis() - startTime < 1000) {
      int loudnessValue = analogRead(loudnessPin);

      unsigned long elapsed = millis() - startTime;
      float timeInSeconds = elapsed / 1000.0;

      // Track when loudness reaches its peak
      if (loudnessValue > peakValue) {
        peakValue = loudnessValue;
        peakTime = timeInSeconds;
      }

      delay(5);  // about 200 samples per second
    }

    // Print only the peak time — this is your "reverberation"
    Serial.println(peakTime, 3);   // e.g., prints "0.823"
  }
}
