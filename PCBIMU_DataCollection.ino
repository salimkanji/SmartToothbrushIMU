/******************************************************************
  ESP32-S3 + BMI270/BMM150 + ReefwingAHRS
  Pins: SDA = GPIO 2, SCL = GPIO 1
******************************************************************/

#include <Wire.h>
#include <math.h>
#include <ReefwingAHRS.h>
#include <Arduino_BMI270_BMM150.h>

#define SDA_PIN  2
#define SCL_PIN  1
#define I2C_HZ   400000

ReefwingAHRS ahrs;
SensorData data;

int loopFrequency = 0;
const unsigned long displayPeriod = 1000;
unsigned long previousMillis = 0;

float prevroll  = 0.0f;
float prevpitch = 0.0f;
float prevyaw   = 0.0f;

void setup() {
  Serial.begin(115200);
  unsigned long startWait = millis();
  while (!Serial && (millis() - startWait < 2000)) { delay(10); }

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(I2C_HZ);

  ahrs.begin();
  ahrs.setFusionAlgorithm(SensorFusion::MADGWICK);
  ahrs.setDeclination(-8.89f);

  Serial.println("ESP32-S3 + BMI270/BMM150 init...");

  if (!IMU.begin()) {
    Serial.println("IMU NOT detected. Check wiring, power, and I2C pins.");
    while (1) { delay(100); }
  }
}

void loop() {
  if (IMU.gyroscopeAvailable())      IMU.readGyroscope     (data.gx, data.gy, data.gz);
  if (IMU.accelerationAvailable())   IMU.readAcceleration  (data.ax, data.ay, data.az);
  if (IMU.magneticFieldAvailable())  IMU.readMagneticField (data.mx, data.my, data.mz);

  ahrs.setData(data);
  ahrs.update();

  if (millis() - previousMillis >= displayPeriod) {

    float newroll  = ahrs.angles.roll;
    float newpitch = ahrs.angles.pitch;
    float newyaw   = ahrs.angles.yaw;

    float deltaroll  = fabsf(newroll  - prevroll);
    float deltapitch = fabsf(newpitch - prevpitch);
    float deltayaw   = fabsf(newyaw   - prevyaw);

    bool stationary = (deltaroll < 3.0f) && (deltapitch < 3.0f) && (deltayaw < 3.0f);

    float beta  = stationary ? 0.05f : 0.4f;
    float alpha = stationary ? 0.9f  : 0.2f;

    ahrs.setBeta(beta);

    prevroll  = alpha * prevroll  + (1.0f - alpha) * newroll;
    prevpitch = alpha * prevpitch + (1.0f - alpha) * newpitch;
    prevyaw   = alpha * prevyaw   + (1.0f - alpha) * newyaw;

    Serial.print(prevroll, 2);  Serial.print("/");
    Serial.print(prevpitch, 2); Serial.print("/");
    Serial.print(prevyaw, 2);   Serial.print("/");

    Serial.print(data.ax, 2); Serial.print("/");
    Serial.print(data.ay, 2); Serial.print("/");
    Serial.print(data.az, 2); Serial.print("/");

    Serial.print(data.gx, 2); Serial.print("/");
    Serial.print(data.gy, 2); Serial.print("/");
    Serial.print(data.gz, 2);

    Serial.print("\n");

    loopFrequency = 0;
    previousMillis = millis();
  }

  loopFrequency++;
}
