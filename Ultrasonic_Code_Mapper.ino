#include "Ultrasonic.h"

Ultrasonic ultrasonic(7);

void setup() {
  Serial.begin(9600);
}

void loop() {
  long rangeInCentimeters = ultrasonic.MeasureInCentimeters();
  Serial.println(rangeInCentimeters);
  delay(500);
}