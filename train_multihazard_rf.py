import json
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import joblib

# ================= LOAD JSONL =================
data = []
with open("logs/fire_data.jsonl", "r") as f:
    for line in f:
        data.append(json.loads(line))

df = pd.DataFrame(data)

print("\n Dataset size:", df.shape)
print(df["hazard_label"].value_counts())

# ================= FEATURES / LABEL =================
X = df[["temp_c", "mq2_hi", "mq135_hi", "voc_ppm"]]
y = df["hazard_label"]

# ================= TRAIN / TEST SPLIT =================
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.25,
    random_state=42,
    stratify=y
)

# ================= MODEL =================
model = RandomForestClassifier(
    n_estimators=200,
    max_depth=12,
    class_weight="balanced",
    random_state=42
)

model.fit(X_train, y_train)

# ================= EVALUATION =================
y_pred = model.predict(X_test)

print("\n Accuracy:", accuracy_score(y_test, y_pred))
print("\n Classification Report:\n")
print(classification_report(
    y_test,
    y_pred,
    target_names=[
        "SAFE",
        "GAS_LEAK",
        "VOC_CHEMICAL",
        "SMOKE_AIR",
        "FIRE"
    ]
))

print("\n Confusion Matrix:")
print(confusion_matrix(y_test, y_pred))

# ================= SAVE MODEL =================
joblib.dump(model, "multihazard_rf_model.pkl")
print("\n Model saved as multihazard_rf_model.pkl")
