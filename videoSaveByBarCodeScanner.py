import cv2
import sys
from collections import deque
import time
import datetime
import requests
import threading
import os

# ---------------- CONFIG ----------------

rtsp_url = 1

frame_rate = 30
pre_buffer_duration = 10  # 10 seconds before scan 1
post_buffer_duration = 20  # 20 seconds after scan 2

pre_buffer_size = pre_buffer_duration * frame_rate
post_buffer_size = post_buffer_duration * frame_rate

video_save_path = "Videos"

# Create videos directory if it doesn't exist
if not os.path.exists(video_save_path):
    os.makedirs(video_save_path)

# ----------------------------------------

pre_buffer = deque(maxlen=pre_buffer_size)  # Circular buffer for pre-recording
recording_frames = []  # Store frames between scan 1 and scan 2
post_buffer = deque(maxlen=post_buffer_size)  # Circular buffer for post-recording

recording = True
cap = None
frame_width = 640
frame_height = 480

barcode_value = None
is_recording = False  # Flag to indicate if we're between scan 1 and scan 2


# ---------------- BARCODE LISTENER ----------------
# Scanner types barcode + presses Enter
def barcode_listener():
    global barcode_value
    while True:
        try:
            code = input("Scan barcode: ")
            if code.strip():
                barcode_value = code.strip()
        except:
            pass


# ---------------- SAVE VIDEO ----------------
def save_video(barcode_1, barcode_2):
    global cap

    barcode_1 = barcode_1.replace('\r', '').replace('\n', '')
    barcode_2 = barcode_2.replace('\r', '').replace('\n', '')
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{video_save_path}/{barcode_1}_to_{barcode_2}_{timestamp}.mp4"

    print(f"\n{'='*60}")
    print(f"Saving video: {output_file}")
    print(f"{'='*60}")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_file, fourcc, frame_rate, (frame_width, frame_height))

    # Save pre-buffer frames (10 seconds before scan 1)
    print(f"Writing pre-buffer: {len(pre_buffer)} frames ({len(pre_buffer)/frame_rate:.2f} seconds)...")
    for buffered_frame in pre_buffer:
        out.write(buffered_frame)

    # Save recording frames (between scan 1 and scan 2)
    print(f"Writing recording: {len(recording_frames)} frames ({len(recording_frames)/frame_rate:.2f} seconds)...")
    for frame in recording_frames:
        out.write(frame)

    # Save post-buffer frames (20 seconds after scan 2)
    print(f"Writing post-buffer: {len(post_buffer)} frames ({len(post_buffer)/frame_rate:.2f} seconds)...")
    for buffered_frame in post_buffer:
        out.write(buffered_frame)

    out.release()

    total_seconds = (len(pre_buffer) + len(recording_frames) + len(post_buffer)) / frame_rate
    print(f"Video saved: {output_file}")
    print(f"Total duration: {total_seconds:.2f} seconds")
    print(f"{'='*60}\n")


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
    print("Instructions:")
    print("1. Scan first barcode to START recording")
    print("2. Scan second barcode to STOP recording")
    print(f"Pre-recording buffer: {pre_buffer_duration} seconds")
    print(f"Post-recording buffer: {post_buffer_duration} seconds")
    print("="*60 + "\n")

    # Start barcode listener in background
    threading.Thread(target=barcode_listener, daemon=True).start()

    barcode_1 = None

    while recording:

        # Capture frame
        ret, frame = cap.read()

        if not ret:
            print("Warning: Frame read failed.")
            time.sleep(0.01)
            continue

        # Always maintain pre-buffer (circular buffer)
        if not is_recording:
            pre_buffer.append(frame)

        # If recording is active (between scan 1 and scan 2)
        if is_recording:
            recording_frames.append(frame)

        # Always maintain post-buffer (circular buffer)
        post_buffer.append(frame)

        # Check if barcode received
        if barcode_value:
            current_barcode = barcode_value
            barcode_value = None

            if not is_recording:
                # First barcode received - START recording
                is_recording = True
                barcode_1 = current_barcode
                recording_frames = []
                
                print(f"\n>>> SCAN 1 - Recording START <<<")
                print(f"Barcode 1: {barcode_1}")
                print(f"Waiting for second barcode to stop...\n")

            else:
                # Second barcode received - STOP recording and prepare for 20 sec post-buffer
                is_recording = False
                barcode_2 = current_barcode
                
                print(f"\n>>> SCAN 2 - Recording STOP <<<")
                print(f"Barcode 2: {barcode_2}")
                print(f"Recording post-buffer for {post_buffer_duration} seconds...")
                
                # Clear post-buffer and record next 20 seconds
                post_buffer.clear()
                post_start_time = time.time()
                
                # Record for 20 seconds after scan 2
                while time.time() - post_start_time < post_buffer_duration and cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        print("Warning: Frame read failed during post-buffer recording.")
                        time.sleep(0.01)
                        continue
                    post_buffer.append(frame)
                    elapsed = time.time() - post_start_time
                    remaining = post_buffer_duration - elapsed
                    print(f"\rPost-buffer recording: {elapsed:.1f}s / {post_buffer_duration}s ({remaining:.1f}s remaining)", end="", flush=True)
                
                print("\n")
                
                # Save the video
                save_video(barcode_1, barcode_2)
                
                # Reset for next recording
                barcode_1 = None
                recording_frames = []
                pre_buffer.clear()
                post_buffer.clear()
                
                print("Ready for next recording. Scan barcode 1...\n")

except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()

finally:
    if cap is not None and cap.isOpened():
        cap.release()

    cv2.destroyAllWindows()
    print("\nApplication closed.")