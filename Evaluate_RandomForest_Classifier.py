import serial
import joblib
from time import sleep
import pandas as pd
import tkinter as tk

# ----------------------------
# SETTINGS
# ----------------------------
PORT = "COM8"
BAUD = 115200
MODEL_PATH = "roll_pitch_classifier-RandomForest.pkl"

class_label = ['left front', 'middle front', 'right front']

# ----------------------------
# MODEL + SERIAL
# ----------------------------
classifier = joblib.load(MODEL_PATH)

dataCOM = serial.Serial(PORT, baudrate=BAUD, timeout=1)
sleep(1)

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


# ----------------------------
# GUI
# ----------------------------
root = tk.Tk()
root.title("Tooth Section Visualizer 🦷")
root.geometry("700x450")

canvas = tk.Canvas(root, width=700, height=320, bg="white")
canvas.pack()

info_frame = tk.Frame(root)
info_frame.pack(fill="x", padx=10, pady=10)

lbl_angles = tk.Label(info_frame, text="Roll: --  Pitch: --  Yaw: --", font=("Arial", 14))
lbl_angles.pack(anchor="w")

lbl_pred = tk.Label(info_frame, text="Predicted Section: --", font=("Arial", 16, "bold"))
lbl_pred.pack(anchor="w", pady=(6, 0))

# Draw a simple mouth outline + “teeth strip”
# Mouth outline
canvas.create_oval(100, 60, 600, 300, outline="black", width=3)

# Teeth bar background
canvas.create_rectangle(160, 150, 540, 220, outline="black", width=2)

# 3 regions (left/middle/right)
region_left = canvas.create_rectangle(160, 150, 286, 220, outline="black", width=2, fill="#e0e0e0")
region_mid  = canvas.create_rectangle(286, 150, 414, 220, outline="black", width=2, fill="#e0e0e0")
region_right= canvas.create_rectangle(414, 150, 540, 220, outline="black", width=2, fill="#e0e0e0")

canvas.create_text(223, 235, text="LEFT", font=("Arial", 12))
canvas.create_text(350, 235, text="MIDDLE", font=("Arial", 12))
canvas.create_text(477, 235, text="RIGHT", font=("Arial", 12))

# Helper to set highlight
def highlight(label: str):
    # Default (dim)
    canvas.itemconfig(region_left,  fill="#e0e0e0")
    canvas.itemconfig(region_mid,   fill="#e0e0e0")
    canvas.itemconfig(region_right, fill="#e0e0e0")

    # Highlight chosen
    if label == "left front":
        canvas.itemconfig(region_left, fill="#7CFC00")  # bright green
    elif label == "middle front":
        canvas.itemconfig(region_mid, fill="#7CFC00")
    elif label == "right front":
        canvas.itemconfig(region_right, fill="#7CFC00")


# Main update loop (non-blocking using root.after)
def update_loop():
    out = readSerial()
    if out is not None:
        roll, pitch, yaw, ax, ay, az, gx, gy, gz = out

        # Build classifier input
        input_df = pd.DataFrame([[roll, pitch, yaw]], columns=["Roll", "Pitch", "Yaw"])

        try:
            predict = classifier.predict(input_df)[0]
            label = class_label[predict]
        except Exception as e:
            label = "--"
            print("Predict error:", e)

        lbl_angles.config(text=f"Roll: {roll:.2f}   Pitch: {pitch:.2f}   Yaw: {yaw:.2f}")
        lbl_pred.config(text=f"Predicted Section: {label.upper() if label != '--' else '--'}")

        if label != "--":
            highlight(label)

    # Run again soon (ms). 20–50ms feels “live”
    root.after(30, update_loop)

# Start loop
update_loop()
root.mainloop()
