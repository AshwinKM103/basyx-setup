"""Wind-turbine telemetry simulator.

Replays simulator/data/wind_turbine_mock.csv over MQTT on a loop, one row every
SIMULATOR_INTERVAL_SECONDS. Every field is taken verbatim from the CSV except the timestamp, which
is stamped with the current wall-clock time on publish so the BaSyx Time Series plugin's relative
time ranges (e.g. "Last 5m") show live data.
"""

import csv
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

CSV_PATH = Path(__file__).parent / "data" / "wind_turbine_mock.csv"
BROKER = os.getenv("MQTT_BROKER", "mosquitto")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "WindTurbine/Telemetry")
INTERVAL_SECONDS = float(os.getenv("SIMULATOR_INTERVAL_SECONDS", "1"))
LOG_LEVEL = os.getenv("SIMULATOR_LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("wind-turbine-simulator")


def build_client() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "wind-turbine-simulator")
    logger.debug("Connecting to MQTT broker %s:%s", BROKER, PORT)
    client.connect(BROKER, PORT)
    client.loop_start()
    return client


def replay_forever(client: mqtt.Client, path: Path) -> None:
    while True:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                payload = {
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "wind_speed": float(row["wind_speed"]),
                    "rotor_rpm": float(row["rotor_rpm"]),
                    "generator_rpm": float(row["generator_rpm"]),
                    "power_output": float(row["power_output"]),
                    "nacelle_temp": float(row["nacelle_temp"]),
                    "gearbox_oil_temp": float(row["gearbox_oil_temp"]),
                    "pitch_angle": float(row["pitch_angle"]),
                    "yaw_angle": float(row["yaw_angle"]),
                    "status": row["status"],
                }
                client.publish(TOPIC, json.dumps(payload))
                logger.debug("Published to %s: %s", TOPIC, payload)
                time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    mqtt_client = build_client()
    try:
        replay_forever(mqtt_client, CSV_PATH)
    except KeyboardInterrupt:
        pass
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
