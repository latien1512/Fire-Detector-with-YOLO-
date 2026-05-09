import json
from collections import Counter

JSONL_FILE = "logs/fire_data.jsonl"

valid_rows = []
hazard_counter = Counter()
invalid_count = 0

with open(JSONL_FILE, "r") as f:
    for line_num, line in enumerate(f, 1):
        try:
            record = json.loads(line)

            # ---- BASIC VALIDATION ----
            required_keys = ["temp_c", "mq2_hi", "mq135_hi", "voc_ppm", "hazard_label"]
            if not all(k in record for k in required_keys):
                invalid_count += 1
                continue

            if record["hazard_label"] not in [0, 1, 2, 3, 4]:
                invalid_count += 1
                continue

            if record["temp_c"] is None:
                invalid_count += 1
                continue

            # ---- VALID ROW ----
            valid_rows.append(record)
            hazard_counter[record["hazard_label"]] += 1

        except Exception as e:
            invalid_count += 1

# ---------- REPORT ----------
print("\n===== DATASET INSPECTION REPORT =====\n")
print(f"Total valid samples : {len(valid_rows)}")
print(f"Invalid / dropped   : {invalid_count}\n")

label_map = {
    0: "SAFE",
    1: "GAS_LEAK",
    2: "VOC_CHEMICAL",
    3: "SMOKE_AIR_QUALITY",
    4: "FIRE"
}

for label, name in label_map.items():
    print(f"{name:<20}: {hazard_counter[label]}")

print("\n====================================\n")

# ---------- SAVE CLEAN DATASET ----------
CLEAN_FILE = "logs/fire_data_clean.jsonl"

with open(CLEAN_FILE, "w") as out:
    for r in valid_rows:
        out.write(json.dumps(r) + "\n")

print(f"✅ Clean dataset saved to: {CLEAN_FILE}")
