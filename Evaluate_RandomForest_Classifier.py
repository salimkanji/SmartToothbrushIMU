import serial
import numpy as np
import joblib
from time import sleep
import pandas as pd

classifier = joblib.load('roll_pitch_classifier-RandomForest.pkl')

dataCOM = serial.Serial('COM8', baudrate=115200, timeout=1)
sleep(1)

class_label = ['left front', 'middle front', 'right front']


def readSerial():
    """
    Returns a consistent 9-tuple:
    (roll, pitch, yaw, ax, ay, az, gx, gy, gz)

    Supports:
      1) CSV4:   now,yaw,pitch,roll
      2) Slash9: roll/pitch/yaw/ax/ay/az/gx/gy/gz

    For CSV4, ax..gz are NaN.
    Returns None for invalid/unexpected lines.
    """
    line = dataCOM.readline().decode('utf-8', errors='ignore').strip()
    if not line:
        return None

    # CSV4: now,yaw,pitch,roll
    if "," in line:
        parts = line.split(",")
        if len(parts) != 4:
            return None
        try:
            t_ms, yaw, pitch, roll = map(float, parts)
        except ValueError:
            return None

        nan = float("nan")
        ax = ay = az = gx = gy = gz = nan
        return roll, pitch, yaw, ax, ay, az, gx, gy, gz

    # Slash9: roll/pitch/yaw/ax/ay/az/gx/gy/gz
    if "/" in line:
        parts = line.split("/")
        if len(parts) != 9:
            return None
        try:
            values = list(map(float, parts))
        except ValueError:
            return None

        roll, pitch, yaw, ax, ay, az, gx, gy, gz = values
        return roll, pitch, yaw, ax, ay, az, gx, gy, gz

    return None


while True:
    out = readSerial()
    if out is None:
        continue

    roll, pitch, yaw, ax, ay, az, gx, gy, gz = out

    input_df = pd.DataFrame([[roll, pitch, yaw]], columns=["Roll", "Pitch","Yaw"])
    predict = classifier.predict(input_df)[0]
    label = class_label[predict]

    print(roll, pitch, yaw)
    print(f"Predicted Section : {label}")
