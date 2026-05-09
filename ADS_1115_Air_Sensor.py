import time, board, busio
from statistics import mean
from adafruit_ads1x15.ads1115 import ADS1115
from adafruit_ads1x15.analog_in import AnalogIn

# ================= CONFIG =================

VCC = 5.0
RL = 20000.0

ALPHA = 0.98
CLEAN_MIN = 0.95
CLEAN_MAX = 1.05
STABLE_TIME = 30
MAX_STEP = 0.02

VOC_ALPHA = 0.25
VOC_BASE_WINDOW = 5

# ================= SETUP ADS1115 =================

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS1115(i2c)
ads.gain = 1

mq135 = AnalogIn(ads, 1)
mq2 = AnalogIn(ads, 0)
voc = AnalogIn(ads, 2)

# ================= INTERNAL STATES =================

_initialized = False

R0_135 = None
R0_2 = None

stable135 = None
stable2 = None

voc_filtered = None

# ================= UTILITIES =================

def calc_rs(v):
    if v <= 0:
        return 1e9
    return RL * (VCC - v) / v

# ================= BASELINE INIT =================

def init_baseline():
    """Khởi tạo R0 và VOC baseline – chỉ chạy 1 lần"""
    global R0_135, R0_2, voc_filtered, _initialized

    if _initialized:
        return

    # MQ-135 baseline
    R0_135 = mean([calc_rs(mq135.voltage) for _ in range(50)])
    time.sleep(0.2)

    # MQ-2 baseline
    R0_2 = mean([calc_rs(mq2.voltage) for _ in range(50)])
    time.sleep(0.2)

    # VOC baseline
    samples = []
    start = time.time()
    while time.time() - start < VOC_BASE_WINDOW:
        samples.append(voc.voltage)
        time.sleep(0.1)

    voc_filtered = mean(samples)

    _initialized = True

# ================= VOC =================

def voc_voltage_to_ppm(v):
    if v < 0.4:
        return 0
    return max(0, min(500, (v - 0.4) * (500 / (2.1 - 0.4))))

def classify_voc(ppm):
    if ppm < 75:
        return "low"
    elif ppm < 150:
        return "medium"
    elif ppm < 300:
        return "high"
    return "very_high"

# ================= MAIN SENSOR FUNCTION =================

def get_air_sensor_data():

    global R0_135, R0_2, stable135, stable2, voc_filtered
    init_baseline()

    # ---------- MQ-135 ----------
    V135 = mq135.voltage
    Rs135 = calc_rs(V135)
    HI135 = R0_135 / Rs135

    if CLEAN_MIN <= HI135 <= CLEAN_MAX:
        if stable135 is None:
            stable135 = time.time()
        elif time.time() - stable135 >= STABLE_TIME:
            R0_135 += max(-R0_135 * MAX_STEP,
                          min(R0_135 * MAX_STEP,
                              ALPHA * R0_135 + (1 - ALPHA) * Rs135 - R0_135))
    else:
        stable135 = None

    # ---------- MQ-2 ----------
    V2 = mq2.voltage
    Rs2 = calc_rs(V2)
    HI2 = R0_2 / Rs2

    if CLEAN_MIN <= HI2 <= CLEAN_MAX:
        if stable2 is None:
            stable2 = time.time()
        elif time.time() - stable2 >= STABLE_TIME:
            R0_2 += max(-R0_2 * MAX_STEP,
                        min(R0_2 * MAX_STEP,
                            ALPHA * R0_2 + (1 - ALPHA) * Rs2 - R0_2))
    else:
        stable2 = None

    # ---------- VOC ----------
    Vvoc = voc.voltage
    voc_filtered = VOC_ALPHA * Vvoc + (1 - VOC_ALPHA) * voc_filtered
    ppm_voc = voc_voltage_to_ppm(voc_filtered)

    return {
        "mq2": {
            "HI": round(HI2, 3),
            "voltage": round(V2, 3)
        },
        "mq135": {
            "HI": round(HI135, 3),
            "voltage": round(V135, 3)
        },
        "voc": {
            "ppm": int(ppm_voc),
            "filtered_v": round(voc_filtered, 3),
            "level": classify_voc(ppm_voc)
        },
        "timestamp": time.time()
    }
