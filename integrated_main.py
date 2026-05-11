import subprocess
import time
import os

PYTHON_PATH = "/home/pi/env_pccc/bin/python"

PROJECT_DIR = "/home/pi/Desktop/Main_Project_Code_Python"
HMI_DIR = "/home/pi/Desktop/Smart_HMI"

FILE_VISION = f"{PROJECT_DIR}/yolo_vision.py"
FILE_HARDWARE = f"{PROJECT_DIR}/main_hazard_detection.py"
FILE_HMI = f"{HMI_DIR}/main_hmi.py"

def start_system():
    print("=" * 65)
    print("🚀 Launching Multi-Process Smart Fire Detection System")
    print("=" * 65)

    os.environ["DISPLAY"] = ":0"
    os.environ["QT_QPA_PLATFORM"] = "wayland"

    try:
        with open("/dev/shm/fire_status.txt", "w") as f:
            f.write("0")
    except Exception as e:
        print(f"⚠️ Cannot create fire_status.txt: {e}")

    print("⏳ Launching YOLO Vision...")
    proc_vision = subprocess.Popen([PYTHON_PATH, FILE_VISION])

    time.sleep(8)

    print("⏳ Launching Hardware + MQTT...")
    proc_hardware = subprocess.Popen([PYTHON_PATH, FILE_HARDWARE])

    time.sleep(2)

    print("⏳ Launching HMI Dashboard...")
    proc_hmi = subprocess.Popen([PYTHON_PATH, FILE_HMI], cwd=HMI_DIR)

    print("\n✅ System is ready! Press Ctrl+C to stop all processes.\n")

    try:
        while True:
            time.sleep(1)

            if proc_vision.poll() is not None:
                print("⚠️ YOLO Vision has stopped!")
                break

            if proc_hardware.poll() is not None:
                print("⚠️ Hardware process has stopped!")
                break

            if proc_hmi.poll() is not None:
                print("⚠️ HMI Dashboard has stopped!")
                break

    except KeyboardInterrupt:
        print("\n🛑 Shutting down the system...")

    finally:
        print("🧹 Cleaning up...")

        for proc in [proc_vision, proc_hardware, proc_hmi]:
            try:
                proc.terminate()
            except:
                pass

        try:
            with open("/dev/shm/fire_status.txt", "w") as f:
                f.write("0")
        except:
            pass

        print("👋 System shutdown complete!")


if __name__ == "__main__":
    start_system()
