/******************************************************************
  ESP32-S3 + BMI270/BMM150 + ReefwingAHRS
  PCB pins: SDA = GPIO2, SCL = GPIO1
  Update rate: ~100 Hz
  Gyro bias calibration at startup
******************************************************************/

#include <Wire.h>
#include <Arduino_BMI270_BMM150.h>
#include <ReefwingAHRS.h>
#include <math.h>

#define SDA_PIN  2
#define SCL_PIN  1
#define I2C_HZ   400000

ReefwingAHRS ahrs;
SensorData data = {};

// Gyro bias offsets (deg/s)
float gxOffset = 0.0f;
float gyOffset = 0.0f;
float gzOffset = 0.0f;

// Output smoothing (EMA)
float yawF = 0.0f, pitchF = 0.0f, rollF = 0.0f;
const float smooth = 0.1f;   // 0.0=no smoothing, 1.0=noisy/raw (try 0.15–0.35)

unsigned long lastUpdate = 0;

// --- Gyro calibration (keep board still) ---
void calibrateGyro() {
  const int N = 500;
  float gx, gy, gz;

  gxOffset = gyOffset = gzOffset = 0.0f;

  Serial.println("Calibrating gyro... DON'T MOVE");

  for (int i = 0; i < N; i++) {
    // wait until gyro sample is available
    while (!IMU.gyroscopeAvailable()) {
      delay(1);
    }
    IMU.readGyroscope(gx, gy, gz);
    gxOffset += gx;
    gyOffset += gy;
    gzOffset += gz;
    delay(2);
  }

  gxOffset /= N;
  gyOffset /= N;
  gzOffset /= N;

  Serial.print("Gyro offsets: ");
  Serial.print(gxOffset, 4); Serial.print(", ");
  Serial.print(gyOffset, 4); Serial.print(", ");
  Serial.println(gzOffset, 4);
}

void setup() {
  Serial.begin(115200);
  delay(1500);   // IMPORTANT on ESP32-S3 USB/CDC

  Serial.println("Booting...");

  // --- I2C on your custom PCB pins ---
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(I2C_HZ);

  // If the IMU lib supports begin(Wire), use it. If not, IMU.begin() will use global Wire.
  // Try this first (many builds will accept it):
  // if (!IMU.begin(Wire)) { ... }
  // If it doesn't compile, fall back to IMU.begin()

  Serial.println("Starting IMU...");
  if (!IMU.begin()) {
    Serial.println("IMU NOT detected. Check wiring/power/I2C pins.");
    while (1) { delay(100); }
  }
  Serial.println("IMU OK");

  calibrateGyro();

  // --- AHRS setup ---
  ahrs.begin();
  ahrs.setDOF(DOF::DOF_9);

  ahrs.setFusionAlgorithm(SensorFusion::MAHONY);
  ahrs.setKp(5.0f);
  ahrs.setKi(0.0f);

  ahrs.setDeclination(-8.51f);

  Serial.println("AHRS ready.");
}

void loop() {
  unsigned long now = millis();

  // ~100 Hz fixed update rate
  if (now - lastUpdate < 10) return;
  lastUpdate = now;

  // Read all sensors if available
  if (IMU.gyroscopeAvailable() &&
      IMU.accelerationAvailable() &&
      IMU.magneticFieldAvailable()) {

    IMU.readGyroscope(data.gx, data.gy, data.gz);
    IMU.readAcceleration(data.ax, data.ay, data.az);
    IMU.readMagneticField(data.mx, data.my, data.mz);

    // Remove gyro bias
    data.gx -= gxOffset;
    data.gy -= gyOffset;
    data.gz -= gzOffset;

    ahrs.setData(data);
    ahrs.update();

    // Smooth angles (optional)
    yawF   = (1.0f - smooth) * yawF   + smooth * ahrs.angles.yaw;
    pitchF = (1.0f - smooth) * pitchF + smooth * ahrs.angles.pitch;
    rollF  = (1.0f - smooth) * rollF  + smooth * ahrs.angles.roll;

    // CSV output: time,yaw,pitch,roll
    Serial.print(now);
    Serial.print(",");
    Serial.print(yawF, 3);
    Serial.print(",");
    Serial.print(pitchF, 3);
    Serial.print(",");
    Serial.println(rollF, 3);
  }
}
