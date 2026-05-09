import time, json, os, csv
from datetime import datetime

from DS18B20_Temperature_Sensor import get_temperature_data
from ADS_1115_Air_Sensor import get_air_sensor_data

# ================= CONFIG =================
LOG_DIR = "logs"
JSONL_FILE = f"{LOG_DIR}/fire_data.jsonl"
CSV_FILE = f"{LOG_DIR}/fire_log.csv"
LOOP_INTERVAL = 1.0

os.makedirs(LOG_DIR, exist_ok=True)

# ================= MANUAL HAZARD LABEL =================
CURRENT_HAZARD = 2
# 0 SAFE
# 1 GAS_LEAK
# 2 VOC_CHEMICAL
# 3 SMOKE_AIR_QUALITY
# 4 FIRE

def hazard_name(label: int) -> str:
    return ["SAFE", "GAS_LEAK", "VOC_CHEMICAL", "SMOKE_AIR_QUALITY", "FIRE"][label]

# ================= CSV SETUP =================
csv_exists = os.path.isfile(CSV_FILE)
csv_file = open(CSV_FILE, mode="a", newline="")
csv_writer = csv.writer(csv_file)

if not csv_exists:
    csv_writer.writerow([
        "date",
        "time",
        "temperature_C",
        "temp_status",
        "mq2_HI",
        "mq135_HI",
        "voc_ppm",
        "hazard"
    ])

print("\n=== FIRE DETECTION SYSTEM – MULTI HAZARD DATA COLLECTION ===\n")

try:
    while True:
        # ---------- READ SENSORS ----------
        temp = get_temperature_data()
        air = get_air_sensor_data()

        now = datetime.now()
        ts_epoch = time.time()

        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        hazard_label = CURRENT_HAZARD
        hazard_str = hazard_name(hazard_label)

        # ---------- JSONL (FOR ML TRAINING) ----------
        ml_record = {
            "ts": round(ts_epoch, 3),
            "temp_c": round(temp["temperature_c"], 2),
            "temp_rise": temp["heat_rise_status"],
            "mq2_hi": round(air["mq2"]["HI"], 3),
            "mq135_hi": round(air["mq135"]["HI"], 3),
            "voc_ppm": int(air["voc"]["ppm"]),
            "hazard_label": hazard_label
        }

        with open(JSONL_FILE, "a") as jf:
            jf.write(json.dumps(ml_record, ensure_ascii=False) + "\n")

        # ---------- CSV LOG (HUMAN READABLE) ----------
        csv_writer.writerow([
            date_str,
            time_str,
            ml_record["temp_c"],
            temp["status"],
            ml_record["mq2_hi"],
            ml_record["mq135_hi"],
            ml_record["voc_ppm"],
            hazard_str
        ])
        csv_file.flush()

        # ---------- TERMINAL OUTPUT ----------
        print("------------------------------------------------")
        print(f" Temp : {ml_record['temp_c']}°C | {temp['status']} | {temp['heat_rise_status']}")
        print(f" MQ2  : {ml_record['mq2_hi']} | MQ135: {ml_record['mq135_hi']}")
        print(f" VOC  : {ml_record['voc_ppm']} ppm")
        print(f" ➡️ LABEL: {hazard_str}")
        print("------------------------------------------------")

        time.sleep(LOOP_INTERVAL)

except KeyboardInterrupt:
    print("\n⛔ System stopped")

finally:
    csv_file.close()
