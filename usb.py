#!/usr/bin/python3
import socket
import sys
from threading import Thread
from datetime import datetime
import cv2
import time

from stream import StreamingServer, StreamingHandler, StreamingOutput, draw_overlay

# --- Settings ---
PORT = 8000
CAMERA_DEVICE_ID = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
TARGET_FPS = 15
JPEG_QUALITY = 70
# ------------

# Get IP address
try:
    connect_interface = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    connect_interface.connect(("8.8.8.8", 80))
    myip = connect_interface.getsockname()[0]
    connect_interface.close()
except OSError:
    myip = '127.0.0.1'

message = 'USB Camera'
if len(sys.argv) > 1:
    message = sys.argv[1]

# HTML page content
PAGE = f"""
<html>
<head>
<title>{message}</title>
</head>
<body>
<img src="stream.mjpg" width="{FRAME_WIDTH}" height="{FRAME_HEIGHT}" />
</body>
</html>
"""

def capture_loop(output):
    """
    Captures frames from a USB camera using OpenCV and writes them to the StreamingOutput.
    """
    cap = cv2.VideoCapture(CAMERA_DEVICE_ID, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"Error: Could not open camera device ID {CAMERA_DEVICE_ID}.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
    print("Camera opened successfully. Starting stream.")

    wait_time = 1.0 / TARGET_FPS

    while True:
        start_time = datetime.now()
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read frame.")
            continue

        # Draw timestamp and message
        draw_overlay(frame, message)

        # Encode frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if ret:
            output.write(buffer.tobytes())

        # Wait to maintain target FPS
        elapsed = (datetime.now() - start_time).total_seconds()
        sleep_time = wait_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

if __name__ == '__main__':
    output = StreamingOutput()
    
    # Start the camera capture in a background thread
    capture_thread = Thread(target=capture_loop, args=(output,), daemon=True)
    capture_thread.start()

    try:
        address = ('', PORT)
        
        # Set the output and page for the handler
        StreamingHandler.output = output
        StreamingHandler.page = PAGE
        
        server = StreamingServer(address, StreamingHandler)
        print(f"Server started. Access at http://{myip}:{PORT}/index.html")
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server.")