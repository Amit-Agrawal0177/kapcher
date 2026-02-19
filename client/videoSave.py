import cv2
import sys
from collections import deque
import time
import socket
import datetime
import requests

HOST = '192.168.1.95'
# HOST = 'localhost'
PORT = 8234
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)
print("Server listening on {}:{}".format(HOST, PORT))


def update_db(name, path):
    try:
        url = "http://localhost:3000/dashboard"  # Replace with your actual API URL

        data = {
            "stationId": "1",
            "orderId" : name,
            "videoUrls": [f"/Videos/{name}.mp4"]
        }
        
        # Define the headers for the request
        headers = {
            "Content-Type": "application/json"
        }

        # Send a POST request with the JSON data and headers
        response = requests.post(url, json=data, headers=headers)

        # Print the response from the server
        print("Status Code:", response.status_code)
        print("Response Text:", response.text)

    except Exception as e:
        print(e)

# # RTSP or webcam stream
rtsp_url = "rtsp://admin:indore@123@192.168.1.110:554/cam/realmonitor"  # Or use a proper RTSP URL

# Video parameters
frame_rate = 30
buffer_duration = 10
buffer_size = buffer_duration * frame_rate
frame_buffer = deque(maxlen=buffer_size)
recording = True
cap = None
frame_width = 320#640
frame_height = 240#480

def save_video(name):
    name = name.replace('\r', '')
    global recording
    output_file = f"/Users/amitagrawal/Downloads/test/public/Videos/{name}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_file, fourcc, frame_rate, (frame_width, frame_height))
    
    # Save buffered frames
    for buffered_frame in frame_buffer:
        out.write(buffered_frame)
    
    print("Recording 20 seconds after trigger...")
    # Record 10 more seconds of video
    end_time = time.time() + buffer_duration
    while time.time() < end_time and cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)
    
    out.release()
    update_db(name, output_file)
    print("Video saved as {}".format(output_file))

try:
    # Initialize video capture first to ensure it's available
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print("Error: Could not open video stream.")
        server_socket.close()
        sys.exit(1)
    
    # Get actual frame dimensions
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    
    # Optional: try setting a buffer size
    cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_duration)
    
    print("Running... Connect to socket and send 'record' to save video.")
    
    # Socket communication in a separate thread or with non-blocking
    conn, addr = server_socket.accept()
    print("Connected by {}".format(addr))
    conn.setblocking(0)  # Non-blocking socket
    
    last_check = time.time()
    check_interval = 0.1  # Check socket every 100ms
    
    while recording:
        # Check socket periodically
        current_time = time.time()
        if current_time - last_check > check_interval:
            try:
                data = conn.recv(1024)
                if data:
                    data_str = data.decode('utf-8', errors='ignore')
                    print("Received: {}".format(data_str))
                    
                    print("Record command received. Saving video...")
                    save_video(data_str)
            except socket.error:
                pass  # No data available or connection error
            last_check = current_time
            
        # Capture frame
        ret, frame = cap.read()
        if not ret:
            print("Warning: Frame read failed. Skipping...")
            time.sleep(0.01)  # Small delay to prevent CPU hogging
            continue
            
        frame_buffer.append(frame)

except Exception as e:
    print(f"Error: {e}")
finally:
    # Cleanup
    if 'conn' in locals():
        conn.close()
    server_socket.close()
    if cap is not None and cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()