import io
import logging
import socket
import socketserver
import sys
import argparse
import time
from http import server
from threading import Condition, Thread
from datetime import datetime

import cv2

# Conditional imports for picamera2
try:
    from picamera2 import Picamera2, MappedArray
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False

# --- Common Streaming Components (from stream.py) ---

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

class StreamingHandler(server.BaseHTTPRequestHandler):
    output = None
    page = ""

    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = self.page.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            self.request.settimeout(5) # 5秒のタイムアウトを設定
            try:
                while True:
                    with self.output.condition:
                        self.output.condition.wait()
                        frame = self.output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except (socket.timeout, BrokenPipeError, ConnectionResetError) as e:
                logging.info("Client disconnected: %s", self.client_address)
            except Exception as e:
                logging.warning('Removed streaming client %s: %s', self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def draw_overlay(frame, message=None, width=None, height=None):
    c1 = (0, 0, 0)
    c2 = (255, 255, 255)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1
    t1 = 5
    t2 = 2
    
    if width is None or height is None:
        height, width, _ = frame.shape

    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    (text_width, text_height), _ = cv2.getTextSize(timestamp, font, scale, t1)
    
    # Adjust position to be in the bottom-right corner
    margin = 10
    ts_pos = (width - text_width - margin, height - text_height + margin)

    cv2.putText(frame, timestamp, ts_pos, font, scale, c1, t1)
    cv2.putText(frame, timestamp, ts_pos, font, scale, c2, t2)
    if message:
        msg_pos = (10, 30)
        cv2.putText(frame, message, msg_pos, font, scale, c1, t1)
        cv2.putText(frame, message, msg_pos, font, scale, c2, t2)

# --- RPi Camera Specific --- (from rpicam.py)

def rpi_draw_timestamp_callback(request):
    message = request.picam2.stream_message
    with MappedArray(request, 'main') as m:
        # widthとheightを渡さず、draw_overlay関数内でフレームのshapeから取得させる
        draw_overlay(m.array, message)

def start_rpi_camera(output, args):
    if not PICAMERA2_AVAILABLE:
        print("Error: picamera2 library is not installed. Please install it to use 'rpi' camera type.")
        sys.exit(1)
    
    picam2 = Picamera2()
    video_config = picam2.create_video_configuration(
        main={"format": "XBGR8888", "size": (args.width, args.height)},
        controls={"FrameRate": args.fps}
    )
    picam2.configure(video_config)
    picam2.stream_message = args.message
    picam2.pre_callback = rpi_draw_timestamp_callback
    
    encoder = JpegEncoder(q=args.quality)
    picam2.start_recording(encoder, FileOutput(output))
    return picam2

# --- USB Camera Specific --- (from usb.py)

def usb_capture_loop(output, args):
    cap = cv2.VideoCapture(args.device_id, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"Error: Could not open camera device ID {args.device_id}.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    print("USB camera opened successfully. Starting stream.")

    wait_time = 1.0 / args.fps

    while True:
        start_time = datetime.now()
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read frame from USB camera.")
            continue

        draw_overlay(frame, args.message, args.width, args.height)

        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])
        if ret:
            output.write(buffer.tobytes())

        elapsed = (datetime.now() - start_time).total_seconds()
        sleep_time = wait_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

# --- Main Execution ---

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Unified camera streamer for Raspberry Pi.")
    parser.add_argument('--camera-type', type=str, required=True, choices=['rpi', 'usb'], help='Type of camera to use.')
    parser.add_argument('--port', type=int, default=8080, help='Port for the web server.')
    parser.add_argument('--width', type=int, default=640, help='Frame width.')
    parser.add_argument('--height', type=int, default=480, help='Frame height.')
    parser.add_argument('--fps', type=int, default=15, help='Frames per second.')
    parser.add_argument('--quality', type=int, default=70, help='JPEG quality (1-100).')
    parser.add_argument('--device-id', type=int, default=0, help='USB camera device ID.')
    parser.add_argument('--message', type=str, default='Camera Stream', help='Message to display on stream.')
    args = parser.parse_args()

    output = StreamingOutput()
    picam2_instance = None

    if args.camera_type == 'rpi':
        args.message = args.message if args.message != 'Camera Stream' else 'RPi Camera'
        picam2_instance = start_rpi_camera(output, args)
    elif args.camera_type == 'usb':
        args.message = args.message if args.message != 'Camera Stream' else 'USB Camera'
        capture_thread = Thread(target=usb_capture_loop, args=(output, args), daemon=True)
        capture_thread.start()

    try:
        # Get IP address
        try:
            connect_interface = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            connect_interface.connect(("8.8.8.8", 80))
            myip = connect_interface.getsockname()[0]
            connect_interface.close()
        except OSError:
            myip = '127.0.0.1'

        # Create and set page content
        PAGE = f'''
        <html><head><title>{args.message}</title></head>
        <body><img src="stream.mjpg" width="{args.width}" height="{args.height}" /></body>
        </html>'''
        StreamingHandler.output = output
        StreamingHandler.page = PAGE

        address = ('', args.port)
        server = StreamingServer(address, StreamingHandler)
        print(f"Server started on {myip}:{args.port}. Camera: {args.camera_type}")
        server.serve_forever()
    finally:
        if picam2_instance:
            picam2_instance.stop_recording()