#include "BluetoothSerial.h"

BluetoothSerial SerialBT;

void setup() {
  Serial.begin(115200);
  SerialBT.begin("ESP32_Bluetooth"); // Имя устройства при поиске
  Serial.println("Bluetooth готов к подключению!");
}

void loop() {
  if (SerialBT.available()) {
    char incomingChar = SerialBT.read();
    SerialBT.print("Принято: ");
    SerialBT.println(incomingChar);
  }
  delay(20);
}