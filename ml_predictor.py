import joblib
import numpy as np
import pandas as pd

# ================= LOAD MODEL =================
MODEL_PATH = "multihazard_rf_model.pkl"
model = joblib.load(MODEL_PATH)

# ================= LABEL MAP =================
LABEL_MAP = {
    0: "SAFE",
    1: "GAS_LEAK",
    2: "VOC_CHEMICAL",
    3: "SMOKE_AIR",
    4: "FIRE"
}

FEATURES = ["temp_c", "mq2_hi", "mq135_hi", "voc_ppm"]

# ================= PREDICT FUNCTION =================
def predict_hazard(temp_c, mq2_hi, mq135_hi, voc_ppm):
    X = pd.DataFrame(
        [[temp_c, mq2_hi, mq135_hi, voc_ppm]],
        columns=FEATURES
    )

    label = model.predict(X)[0]

    return int(label), LABEL_MAP[int(label)]
