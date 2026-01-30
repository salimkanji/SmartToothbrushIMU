import serial
from time import sleep, time
import pandas as pd
import os
import sys
import math

running = True

fileName = 'TrainingYPR_[SUBJECTNAME]_[TRIAL].xlsx'
collectionDuration = 20  # seconds per section test

dataCOM = serial.Serial('COM8', baudrate=115200, timeout=1)
sleep(1)  # allow COM to connect


def readSerial():
    """
    Reads one line from serial and returns a consistent 9-tuple:
    (roll, pitch, yaw, ax, ay, az, gx, gy, gz)

    Supports two formats:
      1) CSV4:   now,yaw,pitch,roll
      2) Slash9: roll/pitch/yaw/ax/ay/az/gx/gy/gz

    For CSV4, raw IMU fields are set to NaN.
    Ignores unexpected / boot / debug lines by returning None.
    """

    line = dataCOM.readline().decode('utf-8', errors='ignore').strip()
    if not line:
        return None

    # --- CSV format: now,yaw,pitch,roll ---
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

    # --- Slash format: roll/pitch/yaw/ax/ay/az/gx/gy/gz ---
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

    # Anything else (boot text, random prints, etc.)
    return None


sections = [
    "right front", "left front", "middle front",
    "upper right base", "upper left base", "upper middle base",
    "lower right base", "lower left base", "lower middle base",
]


def dataCollect(section_name, duration):

    roll_data = []
    pitch_data = []
    yaw_data = []
    ax_data = []
    ay_data = []
    az_data = []
    gx_data = []
    gy_data = []
    gz_data = []
    timestamps = []

    for i in range(5, 0, -1):
        print('Collection will start in: ', i)
        sleep(1)

    print("starting collection")
    startTime = time()

    while time() - startTime < duration:
        out = readSerial()
        if out is None:
            continue

        roll, pitch, yaw, ax, ay, az, gx, gy, gz = out

        roll_data.append(roll)
        pitch_data.append(pitch)
        yaw_data.append(yaw)
        ax_data.append(ax)
        ay_data.append(ay)
        az_data.append(az)
        gx_data.append(gx)
        gy_data.append(gy)
        gz_data.append(gz)

        timestamps.append(time() - startTime)
        print(time() - startTime)

    print("Section: ", section_name, " Data Collected")
    return {
        'Section': [section_name] * len(roll_data),
        "TimeStamp": timestamps,
        "Roll": roll_data,
        "Pitch": pitch_data,
        "Yaw": yaw_data,
        "Ax": ax_data,
        "Ay": ay_data,
        "Az": az_data,
        "Gx": gx_data,
        "Gy": gy_data,
        "Gz": gz_data
    }


# Create the Excel file if it doesn't exist
if not os.path.exists(fileName):
    df = pd.DataFrame({
        'Section': [],
        'TimeStamp': [],
        'Roll': [],
        'Pitch': [],
        'Yaw': [],
        'Ax': [],
        'Ay': [],
        'Az': [],
        'Gx': [],
        'Gy': [],
        'Gz': []
    })
    with pd.ExcelWriter(fileName, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='YPR_Data', index=False)


while running:
    print("Select a section:")
    for i, section in enumerate(sections, 1):
        print(f"{i}: {section}")

    section_choice = int(input("Enter the number corresponding to the section: "))
    current_section = sections[section_choice - 1]

    data = dataCollect(current_section, collectionDuration)
    df = pd.DataFrame(data)

    if os.path.exists(fileName):
        existing_df = pd.read_excel(fileName, sheet_name='YPR_Data')
        df = pd.concat([existing_df, df], ignore_index=True)

    with pd.ExcelWriter(fileName, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df.to_excel(writer, sheet_name='YPR_Data', index=False)

    stop_input = input("Press Q to stop or Enter to continue: ")
    if stop_input.lower() == 'q':
        running = False

dataCOM.close()
print("Data collection ended.")
