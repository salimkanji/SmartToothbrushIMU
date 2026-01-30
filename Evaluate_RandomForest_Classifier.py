import serial
import joblib
from time import sleep
import pandas as pd
import tkinter as tk
from collections import deque

# ----------------------------
# SETTINGS
# ----------------------------
PORT = "COM8"
BAUD = 115200
MODEL_PATH = "roll_pitch_classifier-RandomForest.pkl"

# Map model outputs -> labels
class_label = ['left front', 'middle front', 'right front']

# Smoothing / UI behavior
VOTE_WINDOW = 12          # how many recent predictions to vote over
UPDATE_MS = 30            # GUI refresh rate
CONF_THRESHOLD = 0.55     # below this, show "UNCERTAIN" (if proba available)

# ----------------------------
# MODEL + SERIAL
# ----------------------------
classifier = joblib.load(MODEL_PATH)
has_proba = hasattr(classifier, "predict_proba")

dataCOM = serial.Serial(PORT, baudrate=BAUD, timeout=1)
sleep(1)

def readSerial():
    """
    Returns tuple: (roll, pitch, yaw) or None

    Supports:
      CSV4:   now,yaw,pitch,roll
      Slash9: roll/pitch/yaw/ax/ay/az/gx/gy/gz
    """
    line = dataCOM.readline().decode("utf-8", errors="ignore").strip()
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
        return roll, pitch, yaw

    # Slash9: roll/pitch/yaw/ax/ay/az/gx/gy/gz
    if "/" in line:
        parts = line.split("/")
        if len(parts) != 9:
            return None
        try:
            roll, pitch, yaw, ax, ay, az, gx, gy, gz = map(float, parts)
        except ValueError:
            return None
        return roll, pitch, yaw

    return None

# ----------------------------
# GUI
# ----------------------------
root = tk.Tk()
root.title("Tooth Section Visualizer 🦷 (3-Zone)")
root.geometry("780x520")

canvas = tk.Canvas(root, width=780, height=340, bg="white")
canvas.pack()

info_frame = tk.Frame(root)
info_frame.pack(fill="x", padx=12, pady=10)

lbl_angles = tk.Label(info_frame, text="Roll: --   Pitch: --   Yaw: --", font=("Arial", 14))
lbl_angles.pack(anchor="w")

lbl_pred = tk.Label(info_frame, text="Predicted: --", font=("Arial", 16, "bold"))
lbl_pred.pack(anchor="w", pady=(6, 0))

lbl_conf = tk.Label(info_frame, text="Confidence: --", font=("Arial", 12))
lbl_conf.pack(anchor="w", pady=(4, 0))

# Mouth outline
canvas.create_oval(110, 55, 670, 325, outline="black", width=3)

# Teeth bar background
canvas.create_rectangle(200, 160, 580, 235, outline="black", width=2)

# 3 regions
region_left  = canvas.create_rectangle(200, 160, 326, 235, outline="black", width=2, fill="#e0e0e0")
region_mid   = canvas.create_rectangle(326, 160, 454, 235, outline="black", width=2, fill="#e0e0e0")
region_right = canvas.create_rectangle(454, 160, 580, 235, outline="black", width=2, fill="#e0e0e0")

canvas.create_text(263, 250, text="LEFT", font=("Arial", 12))
canvas.create_text(390, 250, text="MIDDLE", font=("Arial", 12))
canvas.create_text(517, 250, text="RIGHT", font=("Arial", 12))

# History strip (last predictions)
canvas.create_text(120, 20, text="History:", anchor="w", font=("Arial", 12))
history_boxes = []
history_texts = []
HIST_LEN = 30
start_x = 190
y0, y1 = 10, 30
box_w = 16

for i in range(HIST_LEN):
    x0 = start_x + i * (box_w + 2)
    x1 = x0 + box_w
    r = canvas.create_rectangle(x0, y0, x1, y1, outline="#999", fill="#f5f5f5")
    history_boxes.append(r)

def label_to_color(label):
    if label == "left front":
        return "#7CFC00"   # green
    if label == "middle front":
        return "#00BFFF"   # blue-ish
    if label == "right front":
        return "#FFA500"   # orange
    if label == "UNCERTAIN":
        return "#C0C0C0"   # gray
    return "#f5f5f5"

def highlight(label):
    # reset
    canvas.itemconfig(region_left,  fill="#e0e0e0")
    canvas.itemconfig(region_mid,   fill="#e0e0e0")
    canvas.itemconfig(region_right, fill="#e0e0e0")

    if label == "left front":
        canvas.itemconfig(region_left, fill="#7CFC00")
    elif label == "middle front":
        canvas.itemconfig(region_mid, fill="#00BFFF")
    elif label == "right front":
        canvas.itemconfig(region_right, fill="#FFA500")
    elif label == "UNCERTAIN":
        # keep all dim, or lightly tint all
        canvas.itemconfig(region_left,  fill="#dddddd")
        canvas.itemconfig(region_mid,   fill="#dddddd")
        canvas.itemconfig(region_right, fill="#dddddd")

# Smoothing buffer
pred_buffer = deque(maxlen=VOTE_WINDOW)
hist_buffer = deque(maxlen=HIST_LEN)

def majority_vote(buf):
    if not buf:
        return None
    counts = {}
    for x in buf:
        counts[x] = counts.get(x, 0) + 1
    return max(counts, key=counts.get)

def update_history(label):
    hist_buffer.append(label)
    # repaint boxes
    padded = list(hist_buffer)
    padded = ([""] * (HIST_LEN - len(padded))) + padded
    for i, lab in enumerate(padded):
        canvas.itemconfig(history_boxes[i], fill=label_to_color(lab if lab else ""))

def update_loop():
    out = readSerial()
    if out is not None:
        roll, pitch, yaw = out

        # Build classifier input (your model expects Roll, Pitch, Yaw now)
        input_df = pd.DataFrame([[roll, pitch, yaw]], columns=["Roll", "Pitch", "Yaw"])

        conf_text = "--"
        display_label = "--"

        try:
            pred = int(classifier.predict(input_df)[0])  # 0/1/2
            raw_label = class_label[pred]
            pred_buffer.append(raw_label)

            # Confidence (if available)
            conf = None
            if has_proba:
                proba = classifier.predict_proba(input_df)[0]
                conf = float(max(proba))
                conf_text = f"{conf*100:.1f}%"
            else:
                conf_text = "(no predict_proba)"

            # Smoothed label
            voted = majority_vote(pred_buffer)
            display_label = voted if voted is not None else raw_label

            # Uncertain gate (only if proba exists)
            if has_proba and conf is not None and conf < CONF_THRESHOLD:
                display_label = "UNCERTAIN"

        except Exception as e:
            display_label = "UNCERTAIN"
            conf_text = f"err: {e}"

        lbl_angles.config(text=f"Roll: {roll:.2f}   Pitch: {pitch:.2f}   Yaw: {yaw:.2f}")
        lbl_pred.config(text=f"Predicted: {display_label.upper() if display_label != '--' else '--'}")
        lbl_conf.config(text=f"Confidence: {conf_text}")

        highlight(display_label)
        update_history(display_label)

    root.after(UPDATE_MS, update_loop)

update_loop()
root.mainloop()
