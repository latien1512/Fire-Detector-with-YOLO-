import time, json, os, csv
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

from ml_predictor import predict_hazard
from DS18B20_Temperature_Sensor import get_temperature_data
from ADS_1115_Air_Sensor import get_air_sensor_data
from fusion_decision import fusion_decision
from severity_estimator import estimate_severity
from temporal_confirmation import TemporalConfirmation
from relay_control import setup_relays, write_actuators, cleanup_relays
from era_mqtt_client import setup_mqtt, publish_telemetry, stop_mqtt

# ================= ĐỌC TRẠNG THÁI TỪ YOLO =================
STATUS_FILE = "/dev/shm/fire_status.txt"
IMAGE_FILE = "/dev/shm/latest_frame.jpg"

def get_yolo_status():
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r") as f:
                val = f.read().strip()
                if val in ["FIRE", "SMOKE", "SAFE"]:
                    return val
    except:
        pass
    return "SAFE"
# ================= READ MANUAL CONTROL =================
def read_manual_control():
    try:
        with open(MANUAL_FILE, "r") as f:
            return json.load(f)

    except:
        return {
            "mode": "AUTO",
            "buzzer": False,
            "fan": False,
            "mist": False,
            "emergency": False
        }
# ================= HÀM GỬI EMAIL CẢNH BÁO =================
def send_alert_email(subject, body, attach_image=True):
    try:
        with open('/home/pi/Desktop/Main_Project_Code_Python/emailpass.txt', 'r') as f:
            lines = f.read().splitlines()
            sender_email = lines[0]
            password = lines[1]
            receiver_email = lines[2]

        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = receiver_email

        msg.attach(MIMEText(body, 'plain'))

        if attach_image and os.path.exists(IMAGE_FILE):
            with open(IMAGE_FILE, 'rb') as img_f:
                img_data = img_f.read()
                image = MIMEImage(img_data, name="Camera_Snapshot.jpg")
                msg.attach(image)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.send_message(msg)

        print(f" 📧 [SUCCESS] Email with photo report sent: {subject}")

    except Exception as e:
        print(f" ⚠️ [ERROR] Failed to Send Alert Email: {e}")

# ================= TEMPORAL FILTER =================
temporal_filter = TemporalConfirmation(
    safe_confirm_count=5,
    hazard_confirm_count=3
)

# ================= CONFIG =================
LOG_DIR = "logs"

STATE_FILE = "/dev/shm/realtime_state.json"
MANUAL_FILE = "/home/pi/Desktop/Smart_HMI/manual_control.json"
JSONL_FILE = f"{LOG_DIR}/fire_realtime_ml.jsonl"
CSV_FILE = f"{LOG_DIR}/fire_realtime_ml.csv"
LOOP_INTERVAL = 1.0

setup_relays()
setup_mqtt()

os.makedirs(LOG_DIR, exist_ok=True)

# ================= HAZARD NAME =================
def hazard_name(label: int) -> str:
    return ["SAFE", "GAS_LEAK", "VOC_CHEMICAL", "SMOKE_AIR", "FIRE"][label]

# ================= CSV SETUP =================
csv_exists = os.path.isfile(CSV_FILE)
csv_file = open(CSV_FILE, mode="a", newline="")
csv_writer = csv.writer(csv_file)

if not csv_exists:
    csv_writer.writerow([
        "date", "time", "temperature_C", "temp_status", "temp_trend", "heat_rise",
        "mq2_HI", "mq135_HI", "voc_ppm", "severity_score", "severity_level", "action_level",
        "ml_hazard", "fusion_hazard", "fusion_reason", 
        "yolo_status", "final_cross_decision" 
    ])

# ================= EMAIL COOLDOWN SETUP =================
email_cooldowns = {
    "FIRE_CONFIRM": 0,
    "SMOKE_CONFIRM": 0,
    "SUSPECT_FIRE": 0,
    "SUSPECT_SMOKE": 0,
    "GAS_LEAK": 0
}
EMAIL_DELAY = 60

print("\n=== FIRE DETECTION SYSTEM – REALTIME CROSS-VERIFICATION MODE ===\n")

try:
    while True:
        # ---------- READ SENSORS ----------
        temp = get_temperature_data()
        air = get_air_sensor_data()

        now = datetime.now()
        ts_epoch = time.time()

        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        # ---------- FEATURES ----------
        temp_c = round(temp["temperature_c"], 2)
        mq2_hi = round(air["mq2"]["HI"], 3)
        mq135_hi = round(air["mq135"]["HI"], 3)
        voc_ppm = int(air["voc"]["ppm"])
        temp_status = temp["status"]                 # safe / warning / danger
        temp_rise = temp["heat_rise_status"]          # normal / caution / high_risk
        temp_trend = temp["trend"]                    # rising / falling / stable
        
        severity_result = estimate_severity(
            temperature_c=temp_c, heat_rise=temp_rise, mq2_hi=mq2_hi,
            mq135_hi=mq135_hi, voc_ppm=voc_ppm
        )
        
        severity_score = severity_result["severity_score"]
        severity_level = severity_result["severity_level"]
        action_level = severity_result["action_level"]
        severity_reason = severity_result["reason"]

        # ---------- ML PREDICTION ----------
        ml_label, ml_hazard = predict_hazard(
            temp_c=temp_c, mq2_hi=mq2_hi, mq135_hi=mq135_hi, voc_ppm=voc_ppm
        )
        
        # ---------- FUSION DECISION ----------
        fusion_result = fusion_decision(
            temp_c=temp_c, temp_status=temp_status, temp_rise=temp_rise,
            mq2_hi=mq2_hi, mq135_hi=mq135_hi, voc_ppm=voc_ppm,
            ml_label=ml_label, severity_score=severity_score,
            severity_level=severity_level, action_level=action_level,
        )
        fusion_label = fusion_result["label"]
        fusion_hazard = fusion_result["hazard"]
        fusion_reason = fusion_result["reason"]
        fusion_source = fusion_result["source"]
        fusion_urgency = fusion_result["urgency"]
        
        # ---------- TEMPORAL RESULT ----------
        temporal_result = temporal_filter.update(fusion_result)

        confirmed_label = temporal_result["confirmed_label"]
        confirmed_hazard = temporal_result["confirmed_hazard"]
        confirmed_reason = temporal_result["confirmed_reason"]
        relay_active_sensor = temporal_result["relay_active"]
        actuator = temporal_result["actuator"].copy()

        # =================== MA TRẬN ĐỒNG THUẬN QUYẾT ĐỊNH ======================

        yolo_str = get_yolo_status()

        yolo_fire = (yolo_str == "FIRE")
        yolo_smoke = (yolo_str == "SMOKE")

        sensor_fire = (confirmed_hazard == "FIRE")
        sensor_smoke = (confirmed_hazard == "SMOKE_AIR")

        # FINAL DECISION BASED ON FUSION + TEMPORAL
        final_hazard = confirmed_hazard
        final_reason = confirmed_reason
        actuator = temporal_result["actuator"].copy()
        email_to_send = None
        
        # YOLO CROSS-CHECK ONLY
        if yolo_fire:
            final_hazard = "SUSPECT_FIRE"
            final_reason = "FIRE SUSPECTED BY CAMERA"
            actuator.update({
                "buzzer": False,
                "mist": False,
                "fan": True,
                "emergency": False
            })
            email_to_send = "SUSPECT_FIRE"

        elif yolo_smoke and confirmed_hazard not in ["SMOKE_AIR", "FIRE"]:
            final_hazard = "SUSPECT_SMOKE"
            final_reason = "SUSPECT SMOKE: Camera detected smoke but fusion/temporal has not confirmed yet"
            actuator.update({
                "buzzer": False,
                "fan": True,
                "mist": False,
                "emergency": False
            })
            email_to_send = "SUSPECT_SMOKE"

        if confirmed_hazard == "FIRE":
            email_to_send = "FIRE_CONFIRM"

        elif confirmed_hazard == "SMOKE_AIR":
            email_to_send = "SMOKE_CONFIRM"

        elif confirmed_hazard == "GAS_LEAK":
            email_to_send = "GAS_LEAK"
            
        # =================== MANUAL OVERRIDE FROM HMI ========================
        manual = read_manual_control()

        if manual.get("mode") == "MANUAL":
            actuator = {
                "buzzer": bool(manual.get("buzzer", False)),
                "fan": bool(manual.get("fan", False)),
                "mist": bool(manual.get("mist", False)),
                "emergency": bool(manual.get("emergency", False))
            }

            final_reason = "MANUAL OVERRIDE FROM HMI"

        # RELAY ACTIVATED AFTER MANUAL CONTROL IS PROCESSED
        write_actuators(actuator)
        final_relay_active = any(actuator.values())
            
        # ================= SMART EMAIL ALERT SYSTEM =================
        current_time = time.time()

        if email_to_send and (current_time - email_cooldowns[email_to_send] > EMAIL_DELAY):

            sensor_info = f"""
        === RECORDED PHYSICAL PARAMETERS ===
        - Current Temperature: {temp_c}°C ({temp_status})
        - Flammable Gas Level (MQ-2): {mq2_hi}
        - Smoke/Dust Level (MQ-135): {mq135_hi}
        - Harmful VOC Concentration: {voc_ppm} ppm
        ====================================
            """

            subject = ""
            body = ""

            if email_to_send == "FIRE_CONFIRM":
                subject = "🔥 RED ALERT: FIRE CONFIRMED 🔥"
                body = f"The system has CONFIRMED A FIRE through both the AI Camera and Sensors!\n\n- The SIREN and FIRE SUPPRESSION WATER MIST PUMP have been automatically activated.\n- Please check the attached现场 image below and evacuate immediately!\n\n{sensor_info}"

            elif email_to_send == "SMOKE_CONFIRM":
                subject = "🌫 ALERT: DENSE SMOKE CONFIRMED 🌫"
                body = f"The system has CONFIRMED SMOKE through both the AI Camera and Sensors!\n\n- The SIREN and EXHAUST FAN have been automatically activated.\n- Please check the attached image and inspect the area immediately.\n\n{sensor_info}"

            elif email_to_send == "SUSPECT_FIRE":
                subject = "⚠️ WARNING: SUSPECTED FIRE DETECTED ⚠️"
                body = f"The system has detected possible signs of Fire.\n\n- Status: {final_reason}\n- For safety reasons, the fire suppression system has NOT been automatically activated yet.\n- Please verify through the Camera feed. If a real fire is detected, manually activate the pump via the E-Ra application!\n\n{sensor_info}"

            elif email_to_send == "SUSPECT_SMOKE":
                subject = "⚠️ WARNING: SUSPECTED SMOKE DETECTED ⚠️"
                body = f"The system has detected possible signs of Smoke.\n\n- Status: {final_reason}\n- The exhaust fan and siren have NOT been automatically activated to avoid false alarms.\n- Please manually inspect the situation and control the system through the E-Ra application if necessary.\n\n{sensor_info}"

            elif email_to_send == "GAS_LEAK":
                subject = "🚨 EMERGENCY ALERT: GAS LEAK DETECTED 🚨"
                body = f"A dangerous gas leak has been detected! The ventilation fan has been activated automatically. Please inspect and shut off the gas valve immediately!\n\n{sensor_info}"

            send_alert_email(subject, body, attach_image=True)
            email_cooldowns[email_to_send] = current_time

        # ---------- JSONL LOG (ML INFERENCE) ----------
        ml_record = {
            "ts": round(ts_epoch, 3), "temp_c": float(temp_c), "mq2_hi": float(mq2_hi),
            "mq135_hi": float(mq135_hi), "voc_ppm": int(voc_ppm), "ml_hazard_label": int(ml_label)
        }
        with open(JSONL_FILE, "a") as jf:
            jf.write(json.dumps(ml_record, ensure_ascii=False) + "\n")

        # ---------- CSV LOG (HUMAN READABLE) ----------
        csv_writer.writerow([
            date_str, time_str, temp_c, temp_status, temp_trend, temp_rise,
            mq2_hi, mq135_hi, voc_ppm, severity_score, severity_level, action_level,
            ml_hazard, fusion_hazard, fusion_reason, yolo_str, final_reason
        ])
        csv_file.flush()

        # ---------- ERA PAYLOAD ----------
        era_payload = {
            "system_status": final_hazard,
            "temp_c": temp_c, "temp_status": temp_status, "temp_trend": temp_trend, "heat_rise": temp_rise,
            "mq2_hi": mq2_hi, "mq135_hi": mq135_hi, "voc_ppm": voc_ppm,
            "severity_score": severity_score, "severity_level": severity_level, "action_level": action_level,
            "ml_hazard": ml_hazard, "fusion_hazard": fusion_hazard, "fusion_source": fusion_source, "fusion_urgency": fusion_urgency,
            "temporal_hazard": confirmed_hazard, "streak": temporal_result["streak"], "required_count": temporal_result["required_count"],
            "yolo_status": yolo_str,
            "relay_active": final_relay_active,
            "buzzer": actuator.get("buzzer"), "fan": actuator.get("fan"), "mist": actuator.get("mist"), "emergency": actuator.get("emergency")
        }
        mqtt_ok = publish_telemetry(era_payload)

        # ================= REALTIME STATE FOR HMI =================
        realtime_state = {
            "control_mode": manual["mode"],
            "system_status": final_hazard,
            "final_reason": final_reason,

            "temp_c": temp_c,
            "temp_status": temp_status,
            "temp_trend": temp_trend,
            "heat_rise": temp_rise,

            "mq2_hi": mq2_hi,
            "mq135_hi": mq135_hi,
            "voc_ppm": voc_ppm,

            "severity_score": severity_score,
            "severity_level": severity_level,
            "action_level": action_level,
            "severity_reason": severity_reason,

            "ml_hazard": ml_hazard,
            "fusion_hazard": fusion_hazard,
            "fusion_reason": fusion_reason,
            "fusion_source": fusion_source,
            "fusion_urgency": fusion_urgency,

            "yolo_status": yolo_str,

            "confirmed_hazard": confirmed_hazard,
            "confirmed_reason": confirmed_reason,
            "streak": temporal_result["streak"],
            "required_count": temporal_result["required_count"],

            "buzzer": actuator.get("buzzer"),
            "fan": actuator.get("fan"),
            "mist": actuator.get("mist"),
            "emergency": actuator.get("emergency"),

            "timestamp": time.time()
        }
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(realtime_state, f)
        except:
            pass
                
        print(f" ☁️ E-Ra MQTT → {'SENT' if mqtt_ok else 'NOT CONNECTED'}")
        
        # ---------- TERMINAL OUTPUT ----------
        print("================================================")
        print(f" 🌡 Temp : {temp_c} °C | {temp_status} | {temp_trend} | {temp_rise}")
        print(f" 🫁 MQ2  : {mq2_hi} | MQ135 : {mq135_hi}")
        print(f" 💨 VOC  : {voc_ppm} ppm")
        print(f" SEVERITY → {severity_score}/100 | {severity_level} | {action_level}")
        print(f" Severity reason → {severity_reason}")
        print(f" 🤖 ML     → {ml_hazard}\n")
        print(f" 🧠 Result (Fusion based) → {fusion_hazard} ({fusion_source}, {fusion_urgency})")
        print(f" Fusion Reason : {fusion_reason}\n")
        print(f" ⏱ TEMPORAL    → {confirmed_hazard} | streak={temporal_result['streak']}/{temporal_result['required_count']}")
        print(f" 🔌 RELAY (SENSOR) → {'ON' if relay_active_sensor else 'OFF'}")
        print("------------------------------------------------")
        print(f" 📷 YOLO STATUS    → {yolo_str}")
        print(f" 🎯 CROSS-DECISION → {final_hazard}")
        print(f" 📌 Reason         : {final_reason}")
        print("------------------------------------------------")
        print(f" Buzzer   → {'ON' if actuator.get('buzzer') else 'OFF'}")
        print(f" Fan      → {'ON' if actuator.get('fan') else 'OFF'}")
        print(f" Mist     → {'ON' if actuator.get('mist') else 'OFF'}")
        print(f" 🚨 Emergency → {'ON' if actuator.get('emergency') else 'OFF'}")
        print("================================================")

        time.sleep(LOOP_INTERVAL)

except KeyboardInterrupt:
    print("\n⛔ System stopped")

finally:
    cleanup_relays()
    csv_file.close()
    stop_mqtt()
