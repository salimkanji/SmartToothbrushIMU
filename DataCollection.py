import serial
from time import sleep, time
import pandas as pd
import os
import math
import numpy as np

running = True

fileName = 'TrainingYPR_[SUBJECTNAME]_[TRIAL].xlsx'
collectionDuration = 20  # seconds per section test

# --- Serial Port ---
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

    return None


# ----------------------------
# Calibration (zero reference)
# ----------------------------
cal_roll0 = 0.0
cal_pitch0 = 0.0
cal_yaw0 = 0.0
calibrated = False


def flush_serial(seconds=1.0):
    """Flush serial buffer for a bit so calibration uses fresh samples."""
    t0 = time()
    while time() - t0 < seconds:
        _ = dataCOM.readline()


def calibrate_reference(settle_seconds=5, sample_count=50):
    """
    Prompts user to hold the device in a reference pose.
    User presses Enter when ready, then we wait settle_seconds,
    then collect sample_count samples and average Roll/Pitch/Yaw to use as offsets.
    """
    global cal_roll0, cal_pitch0, cal_yaw0, calibrated

    print("\n=== CALIBRATION ===")
    print("Hold the device in front of your face (your chosen 'zero' pose).")
    input("When it is in position, press ENTER to start calibration...")

    print(f"Great — hold still. Settling for {settle_seconds} seconds...")
    flush_serial(0.5)  # clear old lines
    sleep(settle_seconds)

    print("Capturing reference... (stay still)")
    rolls, pitches, yaws = [], [], []
    flush_serial(0.2)

    # Collect sample_count valid samples
    while len(rolls) < sample_count:
        out = readSerial()
        if out is None:
            continue
        roll, pitch, yaw, ax, ay, az, gx, gy, gz = out

        # guard against NaN
        if any(map(lambda v: isinstance(v, float) and math.isnan(v), [roll, pitch, yaw])):
            continue

        rolls.append(roll)
        pitches.append(pitch)
        yaws.append(yaw)

    cal_roll0 = float(np.mean(rolls))
    cal_pitch0 = float(np.mean(pitches))
    cal_yaw0 = float(np.mean(yaws))
    calibrated = True

    print("✅ Calibration complete!")
    print(f"Reference offsets -> Roll0={cal_roll0:.3f}, Pitch0={cal_pitch0:.3f}, Yaw0={cal_yaw0:.3f}")
    print("Yaw will be logged as RELATIVE yaw in [-180, +180].\n")


sections = [
    "right front", "left front", "middle front",
    "upper right base", "upper left base", "upper middle base",
    "lower right base", "lower left base", "lower middle base",
]

EXPECTED_COLS = [
    'Section', 'TimeStamp', 'Roll', 'Pitch', 'Yaw',
    'Ax', 'Ay', 'Az', 'Gx', 'Gy', 'Gz'
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

        # Apply calibration offsets to angles if calibrated
        if calibrated:
            roll -= cal_roll0
            pitch -= cal_pitch0
            # Wrap-safe relative yaw in [-180, 180]
            yaw = (yaw - cal_yaw0 + 180) % 360 - 180

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


# --- Create file if missing, with consistent columns ---
if not os.path.exists(fileName):
    df_init = pd.DataFrame({col: [] for col in EXPECTED_COLS})
    with pd.ExcelWriter(fileName, engine='openpyxl') as writer:
        df_init.to_excel(writer, sheet_name='YPR_Data', index=False)


# Run calibration ONCE before starting section selection
calibrate_reference(settle_seconds=5, sample_count=200)


while running:
    print("Select a section:")
    for i, section in enumerate(sections, 1):
        print(f"{i}: {section}")

    section_choice = int(input("Enter the number corresponding to the section: "))
    current_section = sections[section_choice - 1]

    data = dataCollect(current_section, collectionDuration)
    df = pd.DataFrame(data).reindex(columns=EXPECTED_COLS)

    # enforce consistent dtypes before concat (fixes FutureWarning)
    for col in ["Ax", "Ay", "Az", "Gx", "Gy", "Gz"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if os.path.exists(fileName):
        existing_df = pd.read_excel(fileName, sheet_name='YPR_Data').reindex(columns=EXPECTED_COLS)
        for col in ["Ax", "Ay", "Az", "Gx", "Gy", "Gz"]:
            existing_df[col] = pd.to_numeric(existing_df[col], errors="coerce")

        df = pd.concat([existing_df, df], ignore_index=True)

    with pd.ExcelWriter(fileName, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df.to_excel(writer, sheet_name='YPR_Data', index=False)

    stop_input = input("Press Q to stop or Enter to continue: ")
    if stop_input.lower() == 'q':
        running = False

dataCOM.close()
