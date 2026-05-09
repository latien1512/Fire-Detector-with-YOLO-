import glob
import time
from datetime import datetime

# ================= DS18B20 SETUP =================

base_dir = '/sys/bus/w1/devices/'
device_folders = glob.glob(base_dir + '28*')
if not device_folders:
    raise FileNotFoundError('No DS18B20 devices found under /sys/bus/w1/devices/')

device_folder = device_folders[0]
device_file = device_folder + '/w1_slave'

# ================= INTERNAL STATE =================

_last_temp = None
_last_time = None

# ================= LOW LEVEL =================

def read_temp_raw():
    try:
        with open(device_file, 'r') as f:
            return f.readlines()
    except FileNotFoundError:
        return []

def read_temp_c(retries: int = 50, delay: float = 0.05) -> float:

    for _ in range(retries):
        lines = read_temp_raw()
        if len(lines) >= 2:
            if lines[0].strip().endswith('YES') and 't=' in lines[1]:
                try:
                    temp_str = lines[1].split('t=')[-1]
                    return float(temp_str) / 1000.0
                except (ValueError, IndexError):
                    pass
        time.sleep(delay)

    raise RuntimeError('Failed to read valid temperature from DS18B20')

# ================= LOGIC =================

def get_trend(current, previous):
    if previous is None:
        return 'stable'
    if current > previous + 0.1:
        return 'rising'
    if current < previous - 0.1:
        return 'falling'
    return 'stable'

def get_safety_status(temp):

    if temp < 45:
        return 'safe'
    elif temp < 60:
        return 'warning'
    else:
        return 'danger'

def get_heat_rise_status(delta):

    if delta is None:
        return 'normal'
    if delta < 1.0:
        return 'normal'
    elif delta < 3.0:
        return 'caution'
    else:
        return 'high_risk'

# ================= MAIN API =================

def get_temperature_data():
    
    global _last_temp, _last_time

    temp = read_temp_c()
    now = time.time()

    delta = None
    if _last_temp is not None:
        delta = temp - _last_temp

    data = {
        "node": "ds18b20_1",
        "temperature_c": round(temp, 2),
        "delta_c": round(delta, 2) if delta is not None else 0.0,
        "trend": get_trend(temp, _last_temp),
        "status": get_safety_status(temp),
        "heat_rise_status": get_heat_rise_status(delta),
        "timestamp": datetime.now().isoformat(timespec="milliseconds")
    }

    _last_temp = temp
    _last_time = now
    return data
