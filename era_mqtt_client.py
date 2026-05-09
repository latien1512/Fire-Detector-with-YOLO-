import json
import time
import paho.mqtt.client as mqtt

# ================= E-RA MQTT CONFIG =================
BROKER = "mqtt1.eoh.io"
PORT = 1883
USERNAME = "418a8ce2-89b1-4b1f-b0b5-d6015cc3dc4f"
PASSWORD = "418a8ce2-89b1-4b1f-b0b5-d6015cc3dc4f"
TOPIC_TELEMETRY = "v1/devices/me/telemetry"
TOPIC_RPC = "v1/devices/me/rpc/request/+"
_connected = False

client = mqtt.Client(client_id="pccc_pi01")


def on_connect(client, userdata, flags, rc):
    global _connected
    if rc == 0:
        _connected = True
        print("✅ Connected to E-Ra MQTT")
    else:
        _connected = False
        print(f"❌ MQTT connect failed, rc={rc}")


def on_disconnect(client, userdata, rc):
    global _connected
    _connected = False
    print("⚠ MQTT disconnected")


def setup_mqtt():
    client.username_pw_set(USERNAME, PASSWORD)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.connect(BROKER, PORT, keepalive=60)
    client.loop_start()


def publish_telemetry(payload: dict):
    if not _connected:
        return False

    msg = json.dumps(payload, ensure_ascii=False)
    result = client.publish(TOPIC_TELEMETRY, msg, qos=1)

    return result.rc == mqtt.MQTT_ERR_SUCCESS


def stop_mqtt():
    client.loop_stop()
    client.disconnect()