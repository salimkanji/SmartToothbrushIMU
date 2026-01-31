import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

df = pd.read_excel("TrainingYPR_[SUBJECTNAME]_[TRIAL].xlsx", sheet_name="YPR_Data")

# Keep only the classes you want (optional)
# df = df[df["Section"].isin(["left front","middle front","right front"])]

# Drop missing feature rows
df = df.dropna(subset=["Roll", "Pitch", "Section"])

X = df[["Roll", "Pitch"]]

cat = df["Section"].astype("category")
y = cat.cat.codes
class_label = cat.cat.categories

print("Class counts:\n", cat.value_counts(), "\n")

X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.3,
    random_state=42,
    stratify=y
)

pipeline = make_pipeline(
    StandardScaler(),
    RandomForestClassifier(
        n_estimators=300,
        random_state=42,
        class_weight="balanced"
    )
)

pipeline.fit(X_train, y_train)
y_pred = pipeline.predict(X_test)

print("Classification Report:\n")
print(classification_report(y_test, y_pred, target_names=class_label))

# Normalized confusion matrix (per-actual-class %)
cm = confusion_matrix(y_test, y_pred, normalize="true")
plt.figure(figsize=(7,5))
sns.heatmap(cm, annot=True, fmt=".2f", xticklabels=class_label, yticklabels=class_label, cmap="Blues")
plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.title("Confusion Matrix (Normalized)")
plt.show()

joblib.dump(pipeline, "roll_pitch_classifier-RandomForest.pkl")
print("Saved model: roll_pitch_classifier-RandomForest.pkl")
