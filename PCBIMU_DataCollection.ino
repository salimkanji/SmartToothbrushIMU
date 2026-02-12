/******************************************************************
  ESP32-S3 + BMI270/BMM150 + ReefwingAHRS
  Custom PCB pins: SDA = GPIO2, SCL = GPIO1
  Update rate: ~100 Hz
  Gyro bias calibration at startup

  UPDATED FRAMES (from your drawing):

  (1) IMU:
    +X1 = left
    +Y1 = out of page
    +Z1 = down

  (2) Freedom 6S:
    +X2 = right
    +Y2 = up
    +Z2 = out of page

  Mapping IMU -> Freedom:
    x2 = -x1
    y2 = -z1
    z2 =  y1

  Output CSV:
    time_ms,yaw,pitch,roll
******************************************************************/

#include <Wire.h>
#include <Arduino_BMI270_BMM150.h>
#include <ReefwingAHRS.h>

#define SDA_PIN  2
#define SCL_PIN  1
#define I2C_HZ   400000

// ===== Choose DOF =====
#define USE_9DOF  0   // 0 = 6DOF (gyro+accel), 1 = 9DOF (gyro+accel+mag)

ReefwingAHRS ahrs;
SensorData data = {};

// Gyro bias offsets (deg/s)
float gxOffset = 0.0f, gyOffset = 0.0f, gzOffset = 0.0f;
unsigned long lastUpdate = 0;

// -------- Axis mapping: IMU frame -> Freedom frame --------
static inline void mapIMU_to_Freedom(float &x, float &y, float &z) {
  // Input:  (x1,y1,z1) in IMU frame
  // Output: (x2,y2,z2) in Freedom frame
  float x1 = x, y1 = y, z1 = z;

  x = -x1;   // x2
  y = -z1;   // y2
  z =  y1;   // z2
}

// --- Gyro calibration (keep board still) ---
void calibrateGyro() {
  const int N = 500;
  float gx, gy, gz;
  gxOffset = gyOffset = gzOffset = 0.0f;

  Serial.println("Calibrating gyro... DON'T MOVE");

  for (int i = 0; i < N; i++) {
    while (!IMU.gyroscopeAvailable()) { delay(1); }
    IMU.readGyroscope(gx, gy, gz);
    gxOffset += gx;
    gyOffset += gy;
    gzOffset += gz;
    delay(2);
  }

  gxOffset /= N; gyOffset /= N; gzOffset /= N;

  Serial.print("Gyro offsets: ");
  Serial.print(gxOffset, 4); Serial.print(", ");
  Serial.print(gyOffset, 4); Serial.print(", ");
  Serial.println(gzOffset, 4);
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println("Booting...");

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(I2C_HZ);

  Serial.println("Starting IMU...");
  if (!IMU.begin()) {
    Serial.println("IMU NOT detected. Check wiring/power/I2C pins.");
    while (1) { delay(100); }
  }
  Serial.println("IMU OK");

  calibrateGyro();

  ahrs.begin();

#if USE_9DOF
  ahrs.setDOF(DOF::DOF_9);
#else
  ahrs.setDOF(DOF::DOF_6);
#endif

  ahrs.setFusionAlgorithm(SensorFusion::MAHONY);
  ahrs.setKp(5.0f);
  ahrs.setKi(0.0f);

  // For comparing against a non-magnetic reference:
  ahrs.setDeclination(0.0f);

  Serial.println("AHRS ready.");
  Serial.println("Output: time_ms,yaw,pitch,roll");
}

void loop() {
  unsigned long now = millis();

  // ~100 Hz
  if (now - lastUpdate < 10) return;
  lastUpdate = now;

#if USE_9DOF
  if (IMU.gyroscopeAvailable() && IMU.accelerationAvailable() && IMU.magneticFieldAvailable()) {
#else
  if (IMU.gyroscopeAvailable() && IMU.accelerationAvailable()) {
#endif

    IMU.readGyroscope(data.gx, data.gy, data.gz);
    IMU.readAcceleration(data.ax, data.ay, data.az);

#if USE_9DOF
    IMU.readMagneticField(data.mx, data.my, data.mz);
#else
    data.mx = data.my = data.mz = 0.0f;
#endif

    // remove gyro bias
    data.gx -= gxOffset;
    data.gy -= gyOffset;
    data.gz -= gzOffset;

    // ✅ map into Freedom frame
    mapIMU_to_Freedom(data.gx, data.gy, data.gz);
    mapIMU_to_Freedom(data.ax, data.ay, data.az);
#if USE_9DOF
    mapIMU_to_Freedom(data.mx, data.my, data.mz);
#endif

    ahrs.setData(data);
    ahrs.update();

    Serial.print(now);
    Serial.print(",");
    Serial.print(ahrs.angles.yaw, 3);
    Serial.print(",");
    Serial.print(ahrs.angles.pitch, 3);
    Serial.print(",");
    Serial.println(ahrs.angles.roll, 3);
  }
}
