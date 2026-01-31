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

class_label = ['left front', 'middle front', 'right front']

VOTE_WINDOW = 1
UPDATE_MS = 30
CONF_THRESHOLD = 0.55

CAL_SECONDS = 5
CAL_MIN_SAMPLES = 25

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

    if "," in line:  # CSV4
        parts = line.split(",")
        if len(parts) != 4:
            return None
        try:
            t_ms, yaw, pitch, roll = map(float, parts)
        except ValueError:
            return None
        return roll, pitch, yaw

    if "/" in line:  # Slash9
        parts = line.split("/")
        if len(parts) != 9:
            return None
        try:
            roll, pitch, yaw, ax, ay, az, gx, gy, gz = map(float, parts)
        except ValueError:
            return None
        return roll, pitch, yaw

    return None

def wrap_yaw_rel(y):
    return (y + 180) % 360 - 180

# ----------------------------
# Calibration + prediction state
# ----------------------------
calibrated = False
calibrating_now = False
predicting_enabled = False

cal_roll0 = 0.0
cal_pitch0 = 0.0
cal_yaw0 = 0.0

cal_rolls = []
cal_pitches = []
cal_yaws = []

# ----------------------------
# GUI
# ----------------------------
root = tk.Tk()
root.title("Tooth Section Visualizer 🦷 (3-Zone)")
root.geometry("820x560")

canvas = tk.Canvas(root, width=820, height=340, bg="white")
canvas.pack()

info_frame = tk.Frame(root)
info_frame.pack(fill="x", padx=12, pady=8)

lbl_angles = tk.Label(info_frame, text="Roll: --   Pitch: --   Yaw: --", font=("Arial", 14))
lbl_angles.grid(row=0, column=0, sticky="w")

lbl_pred = tk.Label(info_frame, text="Predicted: --", font=("Arial", 16, "bold"))
lbl_pred.grid(row=1, column=0, sticky="w", pady=(6, 0))

lbl_conf = tk.Label(info_frame, text="Confidence: --", font=("Arial", 12))
lbl_conf.grid(row=2, column=0, sticky="w", pady=(4, 0))

lbl_status = tk.Label(info_frame, text="Status: Click Calibrate", font=("Arial", 12))
lbl_status.grid(row=3, column=0, sticky="w", pady=(6, 0))

btn_frame = tk.Frame(info_frame)
btn_frame.grid(row=0, column=1, rowspan=4, padx=20, sticky="ne")

btn_cal = tk.Button(btn_frame, text="Calibrate (Hold at Face)", font=("Arial", 12, "bold"), width=22)
btn_cal.pack(pady=(0, 6))

lbl_countdown = tk.Label(btn_frame, text="", font=("Arial", 14))
lbl_countdown.pack()

# Mouth outline + regions
canvas.create_oval(120, 55, 700, 325, outline="black", width=3)
canvas.create_rectangle(230, 160, 590, 235, outline="black", width=2)

region_left  = canvas.create_rectangle(230, 160, 350, 235, outline="black", width=2, fill="#e0e0e0")
region_mid   = canvas.create_rectangle(350, 160, 470, 235, outline="black", width=2, fill="#e0e0e0")
region_right = canvas.create_rectangle(470, 160, 590, 235, outline="black", width=2, fill="#e0e0e0")

canvas.create_text(290, 250, text="LEFT", font=("Arial", 12))
canvas.create_text(410, 250, text="MIDDLE", font=("Arial", 12))
canvas.create_text(530, 250, text="RIGHT", font=("Arial", 12))

# History strip
canvas.create_text(120, 20, text="History:", anchor="w", font=("Arial", 12))
history_boxes = []
HIST_LEN = 30
start_x = 190
y0, y1 = 10, 30
box_w = 16

for i in range(HIST_LEN):
    x0 = start_x + i * (box_w + 2)
    x1 = x0 + box_w
    history_boxes.append(canvas.create_rectangle(x0, y0, x1, y1, outline="#999", fill="#f5f5f5"))

def label_to_color(label):
    if label == "left front":
        return "#7CFC00"
    if label == "middle front":
        return "#00BFFF"
    if label == "right front":
        return "#FFA500"
    if label == "UNCERTAIN":
        return "#C0C0C0"
    return "#f5f5f5"

def highlight(label):
    canvas.itemconfig(region_left,  fill="#e0e0e0")
    canvas.itemconfig(region_mid,   fill="#e0e0e0")
    canvas.itemconfig(region_right, fill="#e0e0e0")

    if label == "left front":
        canvas.itemconfig(region_left, fill="#7CFC00")
    elif label == "middle front":
        canvas.itemconfig(region_mid, fill="#00BFFF")
    elif label == "right front":
        canvas.itemconfig(region_right, fill="#FFA500")

pred_buffer = deque(maxlen=VOTE_WINDOW)
hist_buffer = deque(maxlen=HIST_LEN)

def majority_vote(buf):
    if not buf:
        return None
    counts = {}
    for x in buf:
        counts[x] = counts.get(x, 0) + 1
    return max(counts, key=counts.get)

def update_history(label_for_color):
    # store the actual colored label so the strip reflects what you see
    hist_buffer.append(label_for_color)
    padded = list(hist_buffer)
    padded = ([""] * (HIST_LEN - len(padded))) + padded
    for i, lab in enumerate(padded):
        canvas.itemconfig(history_boxes[i], fill=label_to_color(lab if lab else ""))

# ----------------------------
# Calibration
# ----------------------------
def start_calibration():
    global calibrating_now, predicting_enabled, calibrated
    global cal_rolls, cal_pitches, cal_yaws

    if calibrating_now:
        return

    calibrating_now = True
    predicting_enabled = False
    calibrated = False

    pred_buffer.clear()
    hist_buffer.clear()
    highlight("left front")  # just clear later; harmless

    lbl_pred.config(text="Predicted: --")
    lbl_conf.config(text="Confidence: --")

    cal_rolls, cal_pitches, cal_yaws = [], [], []

    btn_cal.config(state="disabled")
    lbl_status.config(text="Status: Calibrating... hold still at your face")
    countdown_tick(CAL_SECONDS)

def countdown_tick(sec_left):
    if sec_left <= 0:
        finalize_calibration()
        return
    lbl_countdown.config(text=f"Calibrating {sec_left}...")
    root.after(1000, lambda: countdown_tick(sec_left - 1))

def finalize_calibration():
    global calibrated, calibrating_now, predicting_enabled
    global cal_roll0, cal_pitch0, cal_yaw0

    calibrating_now = False

    if len(cal_rolls) < CAL_MIN_SAMPLES:
        lbl_countdown.config(text="Calibration failed (no data)")
        lbl_status.config(text="Status: ❌ Calibration failed. Try again.")
        btn_cal.config(state="normal")
        predicting_enabled = False
        calibrated = False
        return

    cal_roll0 = sum(cal_rolls) / len(cal_rolls)
    cal_pitch0 = sum(cal_pitches) / len(cal_pitches)
    cal_yaw0 = sum(cal_yaws) / len(cal_yaws)

    calibrated = True
    predicting_enabled = True

    lbl_countdown.config(text="Done ✅")
    lbl_status.config(text="Status: ✅ Calibrated. Predicting live.")
    btn_cal.config(state="normal")

btn_cal.config(command=start_calibration)

# ----------------------------
# Main update loop
# ----------------------------
def update_loop():
    global cal_rolls, cal_pitches, cal_yaws

    out = readSerial()
    if out is not None:
        roll_raw, pitch_raw, yaw_raw = out

        # Collect raw samples during calibration
        if calibrating_now:
            cal_rolls.append(roll_raw)
            cal_pitches.append(pitch_raw)
            cal_yaws.append(yaw_raw)

        # Apply calibration offsets for display + prediction
        roll = roll_raw
        pitch = pitch_raw
        yaw = yaw_raw

        if calibrated:
            roll = roll_raw - cal_roll0
            pitch = pitch_raw - cal_pitch0
            yaw = wrap_yaw_rel(yaw_raw - cal_yaw0)

        lbl_angles.config(text=f"Roll: {roll:.2f}   Pitch: {pitch:.2f}   Yaw: {yaw:.2f}")

        if predicting_enabled:
            input_df = pd.DataFrame([[roll, pitch]], columns=["Roll", "Pitch"])

            conf_text = "--"
            pred_label_for_color = "--"
            text_label = "--"

            try:
                # Default: use predict() output as label
                pred_idx = int(classifier.predict(input_df)[0])
                pred_label_for_color = class_label[pred_idx]

                conf = None
                if has_proba:
                    proba = classifier.predict_proba(input_df)[0]
                    conf = float(max(proba))
                    conf_text = f"{conf*100:.1f}%"
                else:
                    conf_text = "(no predict_proba)"

                # Optional smoothing (vote window)
                pred_buffer.append(pred_label_for_color)
                voted = majority_vote(pred_buffer)
                if voted is not None:
                    pred_label_for_color = voted

                # If low confidence, show UNCERTAIN text BUT KEEP COLOR of pred_label_for_color
                if has_proba and conf is not None and conf < CONF_THRESHOLD:
                    text_label = f"UNCERTAIN ({pred_label_for_color})"
                else:
                    text_label = pred_label_for_color

            except Exception as e:
                text_label = "UNCERTAIN"
                conf_text = f"err: {e}"
                pred_label_for_color = "--"

            lbl_pred.config(text=f"Predicted: {text_label.upper() if text_label != '--' else '--'}")
            lbl_conf.config(text=f"Confidence: {conf_text}")

            if pred_label_for_color in class_label:
                highlight(pred_label_for_color)
                update_history(pred_label_for_color)

    root.after(UPDATE_MS, update_loop)

lbl_status.config(text="Status: Click Calibrate, hold at face for 5 seconds.")
update_loop()
root.mainloop()
