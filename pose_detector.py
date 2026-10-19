"""
Pose Detection & Gait Telemetry System.
Integrates MediaPipe Pose, MQTT Telemetry, and HTTP Fall Alerts.
"""

import os
import time
import json
import queue
import argparse
import threading
from collections import deque
from datetime import datetime, timezone, timedelta

import cv2
import numpy as np
import requests
import mediapipe as mp
import paho.mqtt.client as mqtt

import config
import image_uploader

# Thread-safe queue for asynchronous notification dispatching
task_queue = queue.Queue()

# Telemetry streaming frequency
MQTT_INTERVAL = 1.0
last_mqtt_time = 0.0


def send_fall_alert_http(image_url: str, timestamp_str: str):
    """Dispatch HTTP POST fall alert payload to Node-RED."""
    payload = {
        "user_id": config.USER_ID,
        "name": config.USER_NAME,
        "location": config.DEVICE_LOCATION,
        "timestamp": timestamp_str,
        "device_id": config.DEVICE_ID,
        "alert_type": "fall_detection",
        "image_url": image_url
    }
    try:
        response = requests.post(config.NODERED_FALL_ALERT_URL, json=payload, timeout=5)
        print(f"[Alert] Node-RED response code: {response.status_code}")
    except Exception as exc:
        print(f"[Alert Error] Failed to send alert to Node-RED: {exc}")


def fall_notification_worker():
    """Background worker thread to upload scene snapshot and trigger notification."""
    print("🚀 Background alert worker started.")
    while True:
        task = task_queue.get()
        if task is None:
            break

        frame, time_str, full_time_str = task
        try:
            cache_dir = "./imgcache"
            os.makedirs(cache_dir, exist_ok=True)

            sanitized_time = time_str.replace(":", "").replace(" ", "_")
            filepath = os.path.join(cache_dir, f"fall_{sanitized_time}.jpg")
            cv2.imwrite(filepath, frame)

            # Upload snapshot (auto-expire after 30 seconds)
            image_url = image_uploader.upload_to_imgbb(filepath, expiration=30)
            if image_url:
                print(f"[Worker] Snapshot uploaded: {image_url}")
                send_fall_alert_http(image_url, full_time_str)
            else:
                print("[Worker] Image upload failed; skipping notification.")
        except Exception as exc:
            print(f"[Worker Error] Notification handling exception: {exc}")
        finally:
            task_queue.task_done()


# Start background alert worker thread
notification_thread = threading.Thread(target=fall_notification_worker, daemon=True)
notification_thread.start()

# Initialize MQTT Client (compatible with paho-mqtt 1.6.x on Python 3.8)
mqtt_client = mqtt.Client()


def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT Telemetry Client connected.")
    else:
        print(f"❌ MQTT Connection failed with return code {rc}")


mqtt_client.on_connect = on_mqtt_connect

try:
    mqtt_client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
    mqtt_client.loop_start()
except Exception as exc:
    print(f"⚠️ MQTT broker connection unavailable: {exc}")

# Initialize MediaPipe Pose
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

# Tracking variables
cog_history = deque(maxlen=30)
prev_landmarks = None
action_labels = ['standing', 'sitting', 'lying', 'squating', 'falling down']
action_history = ['standing']
fall_counter = 0

# Parse CLI arguments
parser = argparse.ArgumentParser(
    description="AIoT Gait Analysis & Fall Detection System",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser.add_argument("--source", type=str, default="falldown1.mp4", help="Video file path or webcam index")
args = parser.parse_args()

video_source = int(args.source) if args.source.isdigit() else args.source
if isinstance(video_source, str) and not os.path.exists(video_source):
    print(f"[Error] Source video file not found: {video_source}")
    exit(1)

cap = cv2.VideoCapture(video_source)
if not cap.isOpened():
    print("[Error] Unable to open video source.")
    exit(1)

window_name = "MediaPipe Pose & Gait Monitor"
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.resizeWindow(window_name, 800, 600)

fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
target_fps = 6.0
frame_interval = max(1, int(fps / target_fps))
frame_idx = 0

with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        frame_idx += 1
        if frame_idx % frame_interval != 0:
            continue

        frame = cv2.resize(frame, (800, 600))
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False

        results = pose.process(rgb_frame)

        rgb_frame.flags.writeable = True
        state_flags = np.zeros(5)

        gait_score = 0.0
        balance_score = 0.0
        sway_index = 0.0
        activity_level = 0.0
        current_state_text = "No Person"

        now_utc8 = datetime.now(timezone(timedelta(hours=8)))
        time_short = now_utc8.strftime("%H:%M:%S")
        time_full = now_utc8.strftime("%Y-%m-%d %H:%M:%S")

        if results.pose_landmarks:
            lm = results.pose_landmarks.landmark

            rs = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
            ls = lm[mp_pose.PoseLandmark.LEFT_SHOULDER]
            rh = lm[mp_pose.PoseLandmark.RIGHT_HIP]
            lh = lm[mp_pose.PoseLandmark.LEFT_HIP]
            rk = lm[mp_pose.PoseLandmark.RIGHT_KNEE]
            lk = lm[mp_pose.PoseLandmark.LEFT_KNEE]
            ra = lm[mp_pose.PoseLandmark.RIGHT_ANKLE]

            scale_y = abs(((rs.y + ls.y) / 2) - ((rh.y + lh.y) / 2))
            scale_x = abs(((rs.x + ls.x) / 2) - ((rh.x + lh.x) / 2))

            # Center of Gravity (CoG) sway index
            cog_x = (ls.x + rs.x + lh.x + rh.x) / 4.0
            cog_history.append(cog_x)
            sway_index = float(np.std(cog_history) * 1000.0)

            # Activity calculation based on landmark displacement
            curr_pts = np.array([[p.x, p.y] for p in lm])
            if prev_landmarks is not None:
                displacement = np.sum(np.linalg.norm(curr_pts - prev_landmarks, axis=1))
                activity_level = float(displacement * 100.0)
            prev_landmarks = curr_pts

            # Pose classification logic
            is_standing = (
                (rk.y - rh.y) * scale_y > 0.02 and
                (lk.y - lh.y) * scale_y > 0.02 and
                (rh.y - rs.y) * scale_y > 0.03
            )
            is_sitting_or_squatting = (
                abs(rk.y - rh.y) * scale_y < 0.02 and
                abs(lk.y - lh.y) * scale_y < 0.02 and
                abs(rh.y - rs.y) * scale_y > 0.03 and
                abs(rk.x - lk.x) * scale_x < 0.003
            )

            if is_standing:
                state_flags[0] = 1
                fall_counter = 0
                if action_history[-1] != action_labels[0]:
                    action_history.append(action_labels[0])
            elif is_sitting_or_squatting:
                idx = 1 if abs(rk.x - ra.x) * scale_x < 0.005 else 3
                state_flags[idx] = 1
                if action_history[-1] != action_labels[idx]:
                    action_history.append(action_labels[idx])
            else:
                trunk_ratio = abs(((rs.y - rh.y) * scale_y) / max(abs(rs.x - rh.x) * scale_x, 1e-4))
                leg_ratio = abs(((rh.y - ra.y) * scale_y) / max(abs(rh.x - ra.x) * scale_x, 1e-4))
                if abs(trunk_ratio - leg_ratio) < 0.2 and not any(state_flags[[0, 1, 3]]):
                    state_flags[2] = 1
                    if action_history[-1] != action_labels[2]:
                        action_history.append(action_labels[2])

            # Sudden change to lying posture from standing indicates a fall
            if state_flags[2]:
                for prev_act in reversed(action_history):
                    if prev_act == "sitting":
                        break
                    if prev_act == "standing":
                        state_flags[4] = 1
                        fall_counter += 1
                        break

            # Estimate balance and gait scores
            if activity_level > 80:
                current_state_text = "Walking"
                balance_score = 0.9
            else:
                current_state_text = "Standing"
                balance_score = max(0.0, min(1.0, 1.0 - (sway_index / 15.0)))
            gait_score = round(80.0 * balance_score + 20.0, 1)

            # Trigger alert condition
            if fall_counter == 50:
                print(f"⚠️ Fall Detected at {time_full}!")
                alert_frame = frame.copy()

                overlays = [
                    (50, "WARNING: FALL DETECTED", (0, 0, 255), 1.2),
                    (100, f"Time: {time_full}", (255, 255, 255), 0.8),
                    (140, f"Name: {config.USER_NAME}", (255, 255, 255), 0.8),
                    (180, f"Loc : {config.DEVICE_LOCATION}", (255, 255, 255), 0.8),
                    (220, f"ID  : {config.USER_ID} ({config.DEVICE_ID})", (255, 255, 255), 0.8),
                ]
                for y, text, color, scale in overlays:
                    cv2.putText(alert_frame, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
                    cv2.putText(alert_frame, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)

                task_queue.put((alert_frame, time_short, time_full))

            if len(action_history) > 30:
                action_history.pop(0)

            # Draw skeleton overlays
            mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)

        # Stream periodic gait metrics via MQTT
        current_epoch = time.time()
        if current_epoch - last_mqtt_time > MQTT_INTERVAL:
            telemetry_payload = {
                "user_id": config.USER_ID,
                "gait_score": gait_score,
                "balance": round(balance_score, 2),
                "activity": round(activity_level, 1),
                "sway": round(sway_index, 1),
                "state": current_state_text
            }
            try:
                mqtt_client.publish(config.MQTT_TOPIC_DATA, json.dumps(telemetry_payload))
            except Exception:
                pass
            last_mqtt_time = current_epoch

        # Display status on preview window
        status_text = "Detect: " + ("falling down" if state_flags[4] else " ".join([action_labels[i] for i, v in enumerate(state_flags) if v]))
        cv2.putText(frame, status_text, (250, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(frame, status_text, (250, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 1, cv2.LINE_AA)

        cv2.imshow(window_name, frame)
        if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
            break

cap.release()
cv2.destroyAllWindows()
mqtt_client.loop_stop()