import serial
import joblib
from time import sleep
from datetime import datetime
import pandas as pd
import customtkinter as ctk
import tkinter as tk
from collections import deque
from pathlib import Path

# ----------------------------
# SETTINGS
# ----------------------------
PORT = "COM14"
BAUD = 115200
MODEL_PATH = "roll_pitch_classifier-RandomForest.pkl"

class_label = ['left front', 'middle front', 'right front']

VOTE_WINDOW = 1
UPDATE_MS = 30
CONF_THRESHOLD = 0.55

CAL_SECONDS = 5
CAL_MIN_SAMPLES = 25

FEEDBACK_CSV = "prediction_feedback_log.csv"

# ----------------------------
# MODEL + SERIAL
# ----------------------------
classifier = joblib.load(MODEL_PATH)
has_proba = hasattr(classifier, "predict_proba")

dataCOM = serial.Serial(PORT, baudrate=BAUD, timeout=1)
sleep(1)

def readSerial():
    line = dataCOM.readline().decode("utf-8", errors="ignore").strip()
    if not line:
        return None

    if "," in line:  # CSV4: now,yaw,pitch,roll
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
# State
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

pred_buffer = deque(maxlen=VOTE_WINDOW)
hist_buffer = deque(maxlen=30)

last_prediction_info = {
    "timestamp": "",
    "roll": None,
    "pitch": None,
    "yaw": None,
    "display_label": "--",
    "raw_label": "--",
    "confidence_text": "--",
    "confidence_value": None
}

def append_feedback_to_csv(is_correct):
    if last_prediction_info["raw_label"] == "--":
        lbl_feedback.configure(text="No prediction to label yet.")
        return

    row = {
        "LoggedAt": datetime.now().isoformat(timespec="seconds"),
        "PredictedSection": last_prediction_info["display_label"],
        "RawPredictedSection": last_prediction_info["raw_label"],
        "ConfidenceText": last_prediction_info["confidence_text"],
        "ConfidenceValue": last_prediction_info["confidence_value"],
        "Roll": last_prediction_info["roll"],
        "Pitch": last_prediction_info["pitch"],
        "Yaw": last_prediction_info["yaw"],
        "UserFeedback": "Correct" if is_correct else "Incorrect",
    }

    out_path = Path(FEEDBACK_CSV)
    df_row = pd.DataFrame([row])
    if out_path.exists():
        df_row.to_csv(out_path, mode="a", header=False, index=False)
    else:
        df_row.to_csv(out_path, mode="w", header=True, index=False)

    lbl_feedback.configure(
        text=f'Logged: {"Correct" if is_correct else "Incorrect"}'
    )


def majority_vote(buf):
    if not buf:
        return None
    counts = {}
    for x in buf:
        counts[x] = counts.get(x, 0) + 1
    return max(counts, key=counts.get)

# ----------------------------
# UI theme
# ----------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("Tooth Section Visualizer 🦷")
app.geometry("980x620")
app.minsize(980, 620)

app.grid_columnconfigure(0, weight=1)
app.grid_columnconfigure(1, weight=0)
app.grid_rowconfigure(0, weight=1)

# ----------------------------
# Left: Canvas card
# ----------------------------
left_card = ctk.CTkFrame(app, corner_radius=18)
left_card.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
left_card.grid_rowconfigure(1, weight=1)
left_card.grid_columnconfigure(0, weight=1)

title = ctk.CTkLabel(left_card, text="Live Mouth View", font=ctk.CTkFont(size=20, weight="bold"))
title.grid(row=0, column=0, padx=16, pady=(16, 10), sticky="w")

canvas = tk.Canvas(left_card, bg="#111111", highlightthickness=0)
canvas.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")

# ----------------------------
# Drawing IDs (so we can redraw cleanly)
# ----------------------------
region_left_id = None
region_mid_id = None
region_right_id = None
history_box_ids = []
label_ids = []
bar_border_id = None
current_color_label = None  # what we currently highlight (for redraw)

# Colors
OUTLINE = "#9CA3AF"
DIM_FILL = "#2A2F3A"
TEXT = "#D1D5DB"
HIST_EMPTY = "#111827"

def zone_color(label):
    if label == "left front":
        return "#22C55E"
    if label == "middle front":
        return "#38BDF8"
    if label == "right front":
        return "#F59E0B"
    return DIM_FILL

def draw_scene():
    """
    Draw everything relative to the current canvas size.
    This runs on startup and whenever the window is resized.
    """
    global region_left_id, region_mid_id, region_right_id
    global history_box_ids, label_ids, bar_border_id

    canvas.delete("all")
    history_box_ids = []
    label_ids = []

    w = max(canvas.winfo_width(), 1)
    h = max(canvas.winfo_height(), 1)
    cx, cy = w / 2, h / 2

    # --- History strip (top, centered) ---
    hist_len = 30
    box_w = max(10, int(w * 0.016))       # scales with width
    box_h = max(16, int(h * 0.045))       # scales with height
    gap = max(3, int(box_w * 0.25))

    total_w = hist_len * box_w + (hist_len - 1) * gap
    hist_x0 = cx - total_w / 2
    hist_y0 = h * 0.06
    hist_y1 = hist_y0 + box_h

    canvas.create_text(hist_x0 - 80, (hist_y0 + hist_y1) / 2,
                       text="History", anchor="w",
                       fill=TEXT, font=("Arial", 12, "bold"))

    for i in range(hist_len):
        x0 = hist_x0 + i * (box_w + gap)
        x1 = x0 + box_w
        rid = canvas.create_rectangle(x0, hist_y0, x1, hist_y1,
                                      outline="#374151", fill=HIST_EMPTY)
        history_box_ids.append(rid)

    # --- Big 3-zone bar (centered) ---
    bar_w = w * 0.65
    bar_h = h * 0.22
    bar_w = max(420, min(bar_w, w * 0.85))
    bar_h = max(110, min(bar_h, h * 0.35))

    bar_x0 = cx - bar_w / 2
    bar_y0 = cy - bar_h / 2
    bar_x1 = cx + bar_w / 2
    bar_y1 = cy + bar_h / 2

    bar_border_id = canvas.create_rectangle(bar_x0, bar_y0, bar_x1, bar_y1,
                                            outline=OUTLINE, width=2)

    third = bar_w / 3

    # Determine fill based on current highlight
    left_fill = zone_color(current_color_label) if current_color_label == "left front" else DIM_FILL
    mid_fill  = zone_color(current_color_label) if current_color_label == "middle front" else DIM_FILL
    right_fill= zone_color(current_color_label) if current_color_label == "right front" else DIM_FILL

    region_left_id = canvas.create_rectangle(bar_x0, bar_y0, bar_x0 + third, bar_y1,
                                             outline=OUTLINE, width=2, fill=left_fill)
    region_mid_id  = canvas.create_rectangle(bar_x0 + third, bar_y0, bar_x0 + 2*third, bar_y1,
                                             outline=OUTLINE, width=2, fill=mid_fill)
    region_right_id= canvas.create_rectangle(bar_x0 + 2*third, bar_y0, bar_x1, bar_y1,
                                             outline=OUTLINE, width=2, fill=right_fill)

    # Labels under bar
    label_y = bar_y1 + max(22, int(h * 0.06))
    label_font = ("Arial", max(12, int(h * 0.03)), "bold")
    label_ids.append(canvas.create_text(bar_x0 + third/2, label_y, text="LEFT", fill=TEXT, font=label_font))
    label_ids.append(canvas.create_text(bar_x0 + third + third/2, label_y, text="MIDDLE", fill=TEXT, font=label_font))
    label_ids.append(canvas.create_text(bar_x0 + 2*third + third/2, label_y, text="RIGHT", fill=TEXT, font=label_font))

    # Repaint history with existing buffer
    repaint_history()

def repaint_history():
    # Paint history boxes based on hist_buffer (right-aligned)
    padded = list(hist_buffer)
    padded = ([""] * (len(history_box_ids) - len(padded))) + padded

    for i, lab in enumerate(padded):
        fill = zone_color(lab) if lab else HIST_EMPTY
        try:
            canvas.itemconfig(history_box_ids[i], fill=fill)
        except Exception:
            pass

def highlight(label):
    global current_color_label
    current_color_label = label

    # Update fills without redrawing everything
    if region_left_id is None:
        return

    canvas.itemconfig(region_left_id, fill=zone_color("left front") if label == "left front" else DIM_FILL)
    canvas.itemconfig(region_mid_id,  fill=zone_color("middle front") if label == "middle front" else DIM_FILL)
    canvas.itemconfig(region_right_id,fill=zone_color("right front") if label == "right front" else DIM_FILL)

def update_history(label_for_color):
    hist_buffer.append(label_for_color)
    repaint_history()

# Redraw on resize (debounced)
_resize_job = None
def on_canvas_resize(event):
    global _resize_job
    if _resize_job is not None:
        app.after_cancel(_resize_job)
    _resize_job = app.after(50, draw_scene)

canvas.bind("<Configure>", on_canvas_resize)

# ----------------------------
# Right: Stats panel
# ----------------------------
right_panel = ctk.CTkFrame(app, corner_radius=18)
right_panel.grid(row=0, column=1, padx=(0, 16), pady=16, sticky="ns")
right_panel.grid_columnconfigure(0, weight=1)

hdr = ctk.CTkLabel(right_panel, text="Live Stats", font=ctk.CTkFont(size=20, weight="bold"))
hdr.grid(row=0, column=0, padx=16, pady=(16, 10), sticky="w")

def make_stat_card(parent, title_text, value_text="--"):
    card = ctk.CTkFrame(parent, corner_radius=14)
    card.grid_columnconfigure(0, weight=1)
    title = ctk.CTkLabel(card, text=title_text, font=ctk.CTkFont(size=12, weight="bold"), text_color="#9CA3AF")
    title.grid(row=0, column=0, padx=12, pady=(10, 0), sticky="w")
    value = ctk.CTkLabel(card, text=value_text, font=ctk.CTkFont(size=18, weight="bold"))
    value.grid(row=1, column=0, padx=12, pady=(4, 10), sticky="w")
    return card, value

card_angles, lbl_angles = make_stat_card(right_panel, "Angles (deg)", "Roll: --  Pitch: --  Yaw: --")
card_angles.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")

card_pred, lbl_pred = make_stat_card(right_panel, "Predicted Section", "--")
card_pred.grid(row=2, column=0, padx=16, pady=(0, 10), sticky="ew")

card_conf, lbl_conf = make_stat_card(right_panel, "Confidence", "--")
card_conf.grid(row=3, column=0, padx=16, pady=(0, 10), sticky="ew")

card_status, lbl_status = make_stat_card(right_panel, "Status", "Click Calibrate")
card_status.grid(row=4, column=0, padx=16, pady=(0, 10), sticky="ew")

controls = ctk.CTkFrame(right_panel, corner_radius=14)
controls.grid(row=5, column=0, padx=16, pady=(0, 16), sticky="ew")
controls.grid_columnconfigure(0, weight=1)

lbl_countdown = ctk.CTkLabel(controls, text="", font=ctk.CTkFont(size=14, weight="bold"))
lbl_countdown.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")

btn_cal = ctk.CTkButton(controls, text="Calibrate (5s)", height=40, corner_radius=12)
btn_cal.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")

feedback_card = ctk.CTkFrame(right_panel, corner_radius=14)
feedback_card.grid(row=6, column=0, padx=16, pady=(0, 16), sticky="ew")
feedback_card.grid_columnconfigure((0, 1), weight=1)

lbl_feedback_title = ctk.CTkLabel(
    feedback_card,
    text="Detection Feedback",
    font=ctk.CTkFont(size=12, weight="bold"),
    text_color="#9CA3AF"
)
lbl_feedback_title.grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 4), sticky="w")

btn_correct = ctk.CTkButton(
    feedback_card,
    text="Correct",
    height=36,
    corner_radius=10,
    command=lambda: append_feedback_to_csv(True)
)
btn_correct.grid(row=1, column=0, padx=(12, 6), pady=(0, 10), sticky="ew")

btn_incorrect = ctk.CTkButton(
    feedback_card,
    text="Incorrect",
    height=36,
    corner_radius=10,
    fg_color="#B91C1C",
    hover_color="#991B1B",
    command=lambda: append_feedback_to_csv(False)
)
btn_incorrect.grid(row=1, column=1, padx=(6, 12), pady=(0, 10), sticky="ew")

lbl_feedback = ctk.CTkLabel(
    feedback_card,
    text="Mark the latest prediction.",
    font=ctk.CTkFont(size=12)
)
lbl_feedback.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="w")


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
    highlight(None)
    repaint_history()

    lbl_pred.configure(text="--")
    lbl_conf.configure(text="--")

    cal_rolls, cal_pitches, cal_yaws = [], [], []

    btn_cal.configure(state="disabled")
    lbl_status.configure(text="Hold at face, stay still")
    countdown_tick(CAL_SECONDS)

def countdown_tick(sec_left):
    if sec_left <= 0:
        finalize_calibration()
        return
    lbl_countdown.configure(text=f"Calibrating {sec_left}...")
    app.after(1000, lambda: countdown_tick(sec_left - 1))

def finalize_calibration():
    global calibrated, calibrating_now, predicting_enabled
    global cal_roll0, cal_pitch0, cal_yaw0

    calibrating_now = False

    if len(cal_rolls) < CAL_MIN_SAMPLES:
        lbl_countdown.configure(text="Calibration failed")
        lbl_status.configure(text="Try again")
        btn_cal.configure(state="normal")
        predicting_enabled = False
        calibrated = False
        return

    cal_roll0 = sum(cal_rolls) / len(cal_rolls)
    cal_pitch0 = sum(cal_pitches) / len(cal_pitches)
    cal_yaw0 = sum(cal_yaws) / len(cal_yaws)

    calibrated = True
    predicting_enabled = True

    lbl_countdown.configure(text="Done ✅")
    lbl_status.configure(text="Calibrated — predicting")
    btn_cal.configure(state="normal")

btn_cal.configure(command=start_calibration)

# ----------------------------
# Main update loop
# ----------------------------
def update_loop():
    global cal_rolls, cal_pitches, cal_yaws
    global cal_roll0, cal_pitch0, cal_yaw0

    out = readSerial()
    if out is not None:
        roll_raw, pitch_raw, yaw_raw = out

        if calibrating_now:
            cal_rolls.append(roll_raw)
            cal_pitches.append(pitch_raw)
            cal_yaws.append(yaw_raw)

        roll = roll_raw
        pitch = pitch_raw
        yaw = yaw_raw

        if calibrated:
            roll = roll_raw - cal_roll0
            pitch = pitch_raw - cal_pitch0
            yaw = wrap_yaw_rel(yaw_raw - cal_yaw0)

        lbl_angles.configure(text=f"Roll: {roll:.2f}  Pitch: {pitch:.2f}  Yaw: {yaw:.2f}")

        if predicting_enabled:
            input_df = pd.DataFrame([[roll, pitch]], columns=["Roll", "Pitch"])

            conf_text = "--"
            pred_label_for_color = "--"
            text_label = "--"

            try:
                pred_idx = int(classifier.predict(input_df)[0])
                pred_label_for_color = class_label[pred_idx]

                conf = None
                if has_proba:
                    proba = classifier.predict_proba(input_df)[0]
                    conf = float(max(proba))
                    conf_text = f"{conf*100:.1f}%"
                else:
                    conf_text = "(no predict_proba)"

                pred_buffer.append(pred_label_for_color)
                voted = majority_vote(pred_buffer)
                if voted is not None:
                    pred_label_for_color = voted

                if has_proba and conf is not None and conf < CONF_THRESHOLD:
                    text_label = f"UNCERTAIN ({pred_label_for_color})"
                else:
                    text_label = pred_label_for_color

            except Exception as e:
                text_label = "UNCERTAIN"
                conf_text = f"err: {e}"
                pred_label_for_color = "--"

            lbl_pred.configure(text=text_label.upper())
            lbl_conf.configure(text=conf_text)

            last_prediction_info["timestamp"] = datetime.now().isoformat(timespec="seconds")
            last_prediction_info["roll"] = round(float(roll), 4)
            last_prediction_info["pitch"] = round(float(pitch), 4)
            last_prediction_info["yaw"] = round(float(yaw), 4)
            last_prediction_info["display_label"] = text_label.upper()
            last_prediction_info["raw_label"] = pred_label_for_color
            last_prediction_info["confidence_text"] = conf_text
            last_prediction_info["confidence_value"] = round(conf, 6) if conf is not None else None

            if pred_label_for_color in class_label:
                highlight(pred_label_for_color)
                update_history(pred_label_for_color)

    app.after(UPDATE_MS, update_loop)

# Initial draw
app.after(50, draw_scene)
lbl_status.configure(text="Click Calibrate, hold at face for 5 seconds.")
update_loop()
app.mainloop()
