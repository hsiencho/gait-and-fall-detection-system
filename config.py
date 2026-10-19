"""
Central configuration module.
Loads environment variables from .env using python-dotenv.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# LINE Bot Credentials
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

# ImgBB API Key
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")

# Node-RED Endpoints
NODERED_FALL_ALERT_URL = os.getenv("NODERED_FALL_ALERT_URL", "http://localhost:1880/fall_alert")
NODERED_GAIT_DATA_URL = os.getenv("NODERED_GAIT_DATA_URL", "http://localhost:1880/gait_data")

# MQTT Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC_DATA = os.getenv("MQTT_TOPIC_DATA", "gait/data")

# Subject & Device Metadata
USER_ID = os.getenv("USER_ID", "U001")
USER_NAME = os.getenv("USER_NAME", "Resident")
DEVICE_LOCATION = os.getenv("LOCATION", "Living Room")
DEVICE_ID = os.getenv("DEVICE_ID", "CAM-01")