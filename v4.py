import cv2
import sys
from collections import deque
import time
import datetime
import requests
import threading
import os
from queue import Queue, Empty

# ---------------- CONFIG ----------------

rtsp_url = 1

frame_rate = 30
pre_buffer_duration = 5
post_buffer_duration = 5

pre_buffer_size = pre_buffer_duration * frame_rate
post_buffer_size = post_buffer_duration * frame_rate

video_save_path = "Videos"

# API CONFIG
API_BASE = "http://192.168.0.135:27189/api"   # change if needed
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJuYW1lIjoiQW1pdCIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc3MTMzMTk2NH0.rnIObtimHttD9IghWrSXfDn2BqKIQbuUJZ7NRFlfacc"                  # paste login token

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}

if not os.path.exists(video_save_path):
    os.makedirs(video_save_path)

# ----------------------------------------

pre_buffer = deque(maxlen=pre_buffer_size)
recording = True
cap = None
frame_width = 640
frame_height = 480

barcode_value = None
is_recording = False
current_packaging_id = None

frame_queue = Queue(maxsize=300)
app_running = True

current_writer = None
current_output_file = None
writer_lock = threading.Lock()

# ---------------- API FUNCTIONS ----------------

def create_packaging_api(barcode1):
    try:
        res = requests.post(
            f"{API_BASE}/packaging/create",
            json={"bar_code_1": barcode1},
            headers=HEADERS
        )

        if res.status_code == 201:
            data = res.json()
            print("Packaging created:", data["packaging_id"])
            return data["packaging_id"]
        else:
            print("Create packaging failed:", res.text)
            return None

    except Exception as e:
        print("Create API error:", e)
        return None


def update_packaging_api(packaging_id, barcode2):
    try:
        res = requests.put(
            f"{API_BASE}/packaging/update/{packaging_id}",
            json={
                "bar_code_2": barcode2,
                "end_time": datetime.datetime.now().isoformat()
            },
            headers=HEADERS
        )

        print("Update response:", res.text)

    except Exception as e:
        print("Update API error:", e)


def upload_video_api(packaging_id, video_path):
    try:
        with open(video_path, "rb") as f:
            files = {"video": f}

            res = requests.post(
                f"{API_BASE}/packaging/upload-video/{packaging_id}",
                files=files,
                headers=HEADERS
            )

        if res.status_code == 200:
            print("Video uploaded successfully")
            return True
        else:
            print("Upload failed:", res.text)
            return False

    except Exception as e:
        print("Upload error:", e)
        return False


# ---------------- BARCODE LISTENER ----------------

def barcode_listener():
    global barcode_value
    while True:
        try:
            code = input("Scan barcode: ")
            if code.strip():
                barcode_value = code.strip()
        except:
            pass


# ---------------- FRAME WRITER THREAD ----------------

def frame_writer_thread():
    global current_writer

    while app_running:
        try:
            try:
                frame_data = frame_queue.get(timeout=1)
            except Empty:
                continue

            if frame_data is None:
                break

            frame_type, frame = frame_data

            with writer_lock:
                if current_writer is not None:
                    current_writer.write(frame)

        except Exception as e:
            print("Error writing frame:", e)


# ---------------- START VIDEO RECORDING ----------------

def start_video_recording(barcode_1, barcode_2):
    global current_writer, current_output_file

    barcode_1 = barcode_1.replace('\r', '').replace('\n', '')
    barcode_2 = barcode_2.replace('\r', '').replace('\n', '')

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    current_output_file = f"{video_save_path}/{barcode_1}_to_{barcode_2}_{timestamp}.mp4"

    print("\n" + "="*60)
    print("Recording to:", current_output_file)
    print("="*60 + "\n")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    current_writer = cv2.VideoWriter(
        current_output_file,
        fourcc,
        frame_rate,
        (frame_width, frame_height)
    )

    if not current_writer.isOpened():
        print("Error: Could not open video writer")
        current_writer = None
        return False

    return True


# ---------------- STOP VIDEO RECORDING ----------------

def stop_video_recording():
    global current_writer, current_output_file

    with writer_lock:
        if current_writer is not None:
            current_writer.release()
            current_writer = None
            print("Video saved:", current_output_file)
            print("="*60 + "\n")


# ---------------- MAIN ----------------

try:
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print("Error: Could not open video stream.")
        sys.exit(1)

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    print("="*60)
    print("Camera started...")
    print("="*60)
    print("Scan first barcode → START")
    print("Scan second barcode → STOP")
    print("="*60 + "\n")

    writer_thread = threading.Thread(target=frame_writer_thread, daemon=False)
    writer_thread.start()

    threading.Thread(target=barcode_listener, daemon=True).start()

    barcode_1 = None
    frames_written = 0

    while recording:

        ret, frame = cap.read()

        if not ret:
            time.sleep(0.01)
            continue

        if not is_recording:
            pre_buffer.append(frame)

        if is_recording:
            try:
                frame_queue.put(("frame", frame), timeout=1)
                frames_written += 1
            except:
                pass

        if barcode_value:
            current_barcode = barcode_value
            barcode_value = None

            # ---------- SCAN 1 ----------
            if not is_recording:

                barcode_1 = current_barcode
                frames_written = 0

                print("\n>>> SCAN 1 - START <<<")
                print("Barcode 1:", barcode_1)

                current_packaging_id = create_packaging_api(barcode_1)

                if not current_packaging_id:
                    print("Packaging creation failed")
                    continue

                is_recording = True

                if not start_video_recording(barcode_1, "processing"):
                    is_recording = False
                    continue

                for pre_frame in pre_buffer:
                    frame_queue.put(("frame", pre_frame))
                    frames_written += 1

            # ---------- SCAN 2 ----------
            else:
                is_recording = False
                barcode_2 = current_barcode

                print("\n>>> SCAN 2 - STOP <<<")
                print("Barcode 2:", barcode_2)

                if current_packaging_id:
                    update_packaging_api(current_packaging_id, barcode_2)

                post_start_time = time.time()

                while time.time() - post_start_time < post_buffer_duration:
                    ret, frame = cap.read()
                    if not ret:
                        continue

                    frame_queue.put(("frame", frame))
                    frames_written += 1

                stop_video_recording()

                final_video_path = None

                if current_output_file:
                    old_file = current_output_file
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_file = f"{video_save_path}/{barcode_1}_to_{barcode_2}_{timestamp}.mp4"

                    try:
                        os.rename(old_file, new_file)
                        final_video_path = new_file
                    except:
                        final_video_path = old_file

                    print("Saved video:", final_video_path)

                    if current_packaging_id and final_video_path:
                        print("Uploading video...")
                        success = upload_video_api(current_packaging_id, final_video_path)

                        if success:
                            try:
                                os.remove(final_video_path)
                                print("Local video deleted")
                            except:
                                print("Could not delete local file")

                barcode_1 = None
                pre_buffer.clear()
                print("Ready for next recording\n")

except Exception as e:
    print("Error:", e)

finally:
    app_running = False
    is_recording = False

    if cap and cap.isOpened():
        cap.release()

    stop_video_recording()
    time.sleep(1)
    frame_queue.put(None)
    writer_thread.join(timeout=5)
    cv2.destroyAllWindows()
    print("Application closed.")
