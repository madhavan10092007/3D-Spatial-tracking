#include <HardwareSerial.h>

HardwareSerial radarSerial(2);

#define RX_PIN 16
#define TX_PIN 17

void setup() {
  Serial.begin(115200);
  radarSerial.begin(115200, SERIAL_8N1, RX_PIN, TX_PIN);
  Serial.println("=========================================");
  Serial.println("MR60BHA1 Final 3D Spatial Vector Locked");
  Serial.println("=========================================");
  delay(1000);
}

void processFrame(uint8_t* f, int len) {
  uint8_t funcWord = f[2];
  uint8_t subWord  = f[3];

  if (funcWord == 0x80 && subWord == 0x05) { 
    // 1. Combine the byte-pairs into true 16-bit numbers
    uint16_t combinedX = (f[6] << 8) | f[7];
    uint16_t combinedY = (f[8] << 8) | f[9];
    uint16_t combinedZ = (f[10] << 8) | f[11];

    float posX = 0.0;
    float posY = 0.0;
    float posZ = 0.0;

    // 2. Decode X (Lateral) using your firmware's 0x8000 sign-offset
    if (combinedX >= 0x8000) {
      posX = (combinedX - 0x8000) / 100.0; // Positive displacement (Right)
    } else {
      posX = (combinedX / 100.0) * -1.0;   // Negative displacement (Left)
    }

    // 3. Decode Y (Depth/Forward distance)
    posY = combinedY / 100.0;

    // 4. Decode Z (Elevation) using 0x8000 sign-offset
    if (combinedZ >= 0x8000) {
      posZ = (combinedZ - 0x8000) / 100.0;
    } else {
      posZ = (combinedZ / 100.0) * -1.0;
    }

    // Print clean, real-world measurements
    Serial.print("🎯 [TARGET TRACKING] ");
    Serial.printf("X: %.2fm (Left/Right) | ", posX);
    Serial.printf("Y: %.2fm (Depth/Forward) | ", posY);
    Serial.printf("Z: %.2fm (Elevation/Height)\n", posZ);
  }
}

void loop() {
  static uint8_t frame[128];
  static int idx = 0;

  while (radarSerial.available()) {
    uint8_t b = radarSerial.read();

    if (idx == 0 && b != 0x53) continue;
    if (idx == 1 && b != 0x59) { idx = 0; continue; }

    frame[idx++] = b;

    if (idx >= 128) { idx = 0; continue; }

    // Lock parser strictly onto your 15-byte 3D Coordinate packets
    if (idx >= 15 && b == 0x43 && frame[idx-2] == 0x54) {
      processFrame(frame, idx);
      idx = 0;
    }
  }
  delay(10);
}