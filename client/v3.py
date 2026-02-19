#video save successfully tested

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
recording = True
cap = None
frame_width = 640
frame_height = 480

barcode_value = None
is_recording = False

# Queue for real-time frame writing
frame_queue = Queue(maxsize=300)  # Limit queue size to prevent memory overload
app_running = True

# Video writer control
current_writer = None
current_output_file = None
writer_lock = threading.Lock()


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
    """Thread that writes frames to disk in real-time"""
    global current_writer, current_output_file
    
    while app_running:
        try:
            try:
                frame_data = frame_queue.get(timeout=1)
            except Empty:
                continue
            
            if frame_data is None:  # Shutdown signal
                break
            
            frame_type, frame = frame_data
            
            # Write frame to current video writer
            with writer_lock:
                if current_writer is not None:
                    current_writer.write(frame)
                    
        except Exception as e:
            print(f"Error writing frame: {e}")


# ---------------- START VIDEO RECORDING ----------------
def start_video_recording(barcode_1, barcode_2):
    """Initialize video writer for real-time saving"""
    global current_writer, current_output_file
    
    barcode_1 = barcode_1.replace('\r', '').replace('\n', '')
    barcode_2 = barcode_2.replace('\r', '').replace('\n', '')
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    current_output_file = f"{video_save_path}/{barcode_1}_to_{barcode_2}_{timestamp}.mp4"
    
    print(f"\n{'='*60}")
    print(f"Recording to: {current_output_file}")
    print(f"{'='*60}\n")
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    current_writer = cv2.VideoWriter(current_output_file, fourcc, frame_rate, (frame_width, frame_height))
    
    if not current_writer.isOpened():
        print(f"Error: Could not open video writer for {current_output_file}")
        current_writer = None
        return False
    
    return True


# ---------------- STOP VIDEO RECORDING ----------------
def stop_video_recording():
    """Close the current video writer"""
    global current_writer, current_output_file
    
    with writer_lock:
        if current_writer is not None:
            current_writer.release()
            current_writer = None
            print(f"Video saved: {current_output_file}")
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

    # Start frame writer thread
    writer_thread = threading.Thread(target=frame_writer_thread, daemon=False)
    writer_thread.start()

    # Start barcode listener in background
    threading.Thread(target=barcode_listener, daemon=True).start()

    barcode_1 = None
    frames_written = 0

    while recording:

        # Capture frame
        ret, frame = cap.read()

        if not ret:
            print("Warning: Frame read failed.")
            time.sleep(0.01)
            continue

        # Always maintain pre-buffer (circular buffer) when not recording
        if not is_recording:
            pre_buffer.append(frame)
        
        # If recording is active (between scan 1 and scan 2) - queue frames for writing
        if is_recording:
            try:
                frame_queue.put(("frame", frame), timeout=1)
                frames_written += 1
            except:
                print("Warning: Frame queue full, skipping frame")

        # Check if barcode received
        if barcode_value:
            current_barcode = barcode_value
            barcode_value = None

            if not is_recording:
                # First barcode received - START recording
                is_recording = True
                barcode_1 = current_barcode
                frames_written = 0
                
                print(f"\n>>> SCAN 1 - Recording START <<<")
                print(f"Barcode 1: {barcode_1}")
                print(f"Writing pre-buffer ({len(pre_buffer)} frames)...")
                
                # Start video recording
                if not start_video_recording(barcode_1, "processing"):
                    is_recording = False
                    continue
                
                # Queue pre-buffer frames
                for pre_frame in pre_buffer:
                    frame_queue.put(("frame", pre_frame))
                    frames_written += 1
                
                print(f"Pre-buffer queued. Waiting for second barcode...\n")

            else:
                # Second barcode received - STOP recording and record post-buffer
                is_recording = False
                barcode_2 = current_barcode
                
                print(f"\n>>> SCAN 2 - Recording STOP <<<")
                print(f"Barcode 2: {barcode_2}")
                print(f"Recording {post_buffer_duration} sec post-buffer...")
                
                post_start_time = time.time()
                
                # Record for 20 seconds after scan 2
                while time.time() - post_start_time < post_buffer_duration and cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        print("Warning: Frame read failed during post-buffer recording.")
                        time.sleep(0.01)
                        continue
                    
                    # Queue frame for writing
                    try:
                        frame_queue.put(("frame", frame), timeout=1)
                        frames_written += 1
                    except:
                        print("Warning: Frame queue full, skipping frame")
                    
                    elapsed = time.time() - post_start_time
                    remaining = post_buffer_duration - elapsed
                    print(f"\rPost-buffer recording: {elapsed:.1f}s / {post_buffer_duration}s ({remaining:.1f}s remaining)", end="", flush=True)
                
                print("\n")
                
                # Stop recording and update filename
                stop_video_recording()
                
                # Rename file to include barcode_2
                if current_output_file:
                    old_file = current_output_file
                    barcode_2_clean = barcode_2.replace('\r', '').replace('\n', '')
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_file = f"{video_save_path}/{barcode_1}_to_{barcode_2_clean}_{timestamp}.mp4"
                    try:
                        os.rename(old_file, new_file)
                        print(f"File renamed to: {new_file}")
                    except:
                        print(f"Saved as: {old_file}")
                
                # Reset for next recording
                barcode_1 = None
                pre_buffer.clear()
                
                print(f"Total frames written: {frames_written}")
                print("Ready for next recording. Scan barcode 1...\n")

except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()

finally:
    app_running = False
    is_recording = False
    
    if cap is not None and cap.isOpened():
        cap.release()

    # Stop video recording if active
    stop_video_recording()
    
    # Wait briefly for queue to flush
    print("Flushing remaining frames...")
    time.sleep(1)
    
    # Send shutdown signal
    frame_queue.put(None)
    writer_thread.join(timeout=5)

    cv2.destroyAllWindows()
    print("Application closed.")