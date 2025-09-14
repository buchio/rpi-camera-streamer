import io
import sys
import argparse
import time
import logging
from threading import Condition, Thread
from datetime import datetime
import socket

import cv2
import numpy as np
from flask import Flask, Response, render_template_string

# Conditional imports for picamera2
try:
    from picamera2 import Picamera2, MappedArray
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False

# Conditional imports for sounddevice
try:
    import sounddevice as sd
    import soundfile as sf
    SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    SOUNDDEVICE_AVAILABLE = False

# --- Thread-Safe Buffer for Streaming ---

class StreamBuffer(io.BufferedIOBase):
    def __init__(self):
        self.data = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.data = buf
            self.condition.notify_all()

    def read(self):
        with self.condition:
            self.condition.wait()
            return self.data

# --- Video and Audio Capture Threads ---

def draw_overlay(frame, message=None):
    c1 = (0, 0, 0)
    c2 = (255, 255, 255)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1
    t1 = 5
    t2 = 2
    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    ts_pos = (frame.shape[1] - 380, frame.shape[0] - 10)
    cv2.putText(frame, timestamp, ts_pos, font, scale, c1, t1)
    cv2.putText(frame, timestamp, ts_pos, font, scale, c2, t2)
    if message:
        msg_pos = (10, 30)
        cv2.putText(frame, message, msg_pos, font, scale, c1, t1)
        cv2.putText(frame, message, msg_pos, font, scale, c2, t2)

def rpi_video_capture_thread(buffer, args):
    if not PICAMERA2_AVAILABLE:
        logging.error("picamera2 library is not installed. Please install it to use 'rpi' camera type.")
        return

    picam2 = Picamera2()
    video_config = picam2.create_video_configuration(
        main={"format": "XBGR8888", "size": (args.width, args.height)},
        controls={"FrameRate": args.fps}
    )
    picam2.configure(video_config)
    
    encoder = JpegEncoder(q=args.quality)
    
    # Custom output to draw overlay before encoding
    class JpegOutput(io.BufferedIOBase):
        def write(self, b):
            # b is the encoded JPEG data
            buffer.write(b)

    output = JpegOutput()

    # Callback to draw on the frame before encoding
    def pre_callback(request):
        with MappedArray(request, "main") as m:
            draw_overlay(m.array, args.message)

    picam2.pre_callback = pre_callback
    picam2.start_recording(encoder, FileOutput(output))
    logging.info("RPi camera recording started.")
    try:
        while True:
            time.sleep(1)
    finally:
        picam2.stop_recording()
        logging.info("RPi camera recording stopped.")


def usb_video_capture_thread(buffer, args):
    cap = cv2.VideoCapture(args.device_id, cv2.CAP_V4L2)
    if not cap.isOpened():
        logging.error(f"Could not open camera device ID {args.device_id}.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    logging.info("USB camera opened successfully. Starting stream.")

    wait_time = 1.0 / args.fps

    while True:
        start_time = datetime.now()
        ret, frame = cap.read()
        if not ret:
            logging.warning("Could not read frame from USB camera.")
            continue

        draw_overlay(frame, args.message)

        ret, encoded_frame = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])
        if ret:
            buffer.write(encoded_frame.tobytes())

        elapsed = (datetime.now() - start_time).total_seconds()
        sleep_time = wait_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

def audio_capture_thread(buffer, args):
    if not SOUNDDEVICE_AVAILABLE:
        logging.error("sounddevice or soundfile library is not available. Audio streaming is disabled.")
        return

    samplerate = args.audio_samplerate
    channels = args.audio_channels
    blocksize = int(samplerate * args.audio_duration / 1000) # blocksize in samples

    logging.info(f"Audio stream started with samplerate={samplerate}, channels={channels}.")
    
    try:
        def callback(indata, frames, time, status):
            if status:
                logging.warning(status)
            # Using a temporary in-memory file to write WAV data
            with io.BytesIO() as f:
                sf.write(f, indata, samplerate, format='WAV', subtype='PCM_16')
                buffer.write(f.getvalue())

        with sd.InputStream(samplerate=samplerate, channels=channels, blocksize=blocksize, callback=callback):
            while True:
                time.sleep(10)
    except Exception as e:
        logging.error(f"Audio capture failed: {e}")


# --- Flask Web Application ---

app = Flask(__name__)
video_buffer = StreamBuffer()
audio_buffer = StreamBuffer()

@app.route('/')
def index():
    use_audio = args.enable_audio and SOUNDDEVICE_AVAILABLE
    return render_template_string('''
        <html>
        <head>
            <title>{{ message }}</title>
        </head>
        <body>
            <h1>{{ message }}</h1>
            <img src="{{ url_for('video_feed') }}" width="{{ width }}" height="{{ height }}">
            {% if use_audio %}
                <h2>Audio Stream</h2>
                <audio controls autoplay>
                    <source src="{{ url_for('audio_feed') }}" type="audio/wav">
                    Your browser does not support the audio element.
                </audio>
            {% endif %}
        </body>
        </html>
    ''', message=args.message, width=args.width, height=args.height, use_audio=use_audio)

def gen_video():
    while True:
        frame = video_buffer.read()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

def gen_audio():
    while True:
        chunk = audio_buffer.read()
        yield chunk

@app.route('/video_feed')
def video_feed():
    return Response(gen_video(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/audio_feed')
def audio_feed():
    if not args.enable_audio or not SOUNDDEVICE_AVAILABLE:
        return "Audio stream not available or not enabled.", 404
    return Response(gen_audio(), mimetype='audio/wav')


# --- Main Execution ---

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Unified camera streamer for Raspberry Pi using Flask.")
    # General
    parser.add_argument('--camera-type', type=str, required=True, choices=['rpi', 'usb'], help='Type of camera to use.')
    parser.add_argument('--port', type=int, default=8080, help='Port for the web server.')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host address for the web server.')
    parser.add_argument('--message', type=str, default='Camera Stream', help='Message to display on stream.')
    # Video
    parser.add_argument('--width', type=int, default=640, help='Frame width.')
    parser.add_argument('--height', type=int, default=480, help='Frame height.')
    parser.add_argument('--fps', type=int, default=15, help='Frames per second.')
    parser.add_argument('--quality', type=int, default=70, help='JPEG quality (1-100).')
    # USB Specific
    parser.add_argument('--device-id', type=int, default=0, help='USB camera device ID.')
    # Audio Specific
    parser.add_argument('--enable-audio', action='store_true', help='Enable audio streaming.')
    parser.add_argument('--audio-samplerate', type=int, default=44100, help='Audio sample rate in Hz.')
    parser.add_argument('--audio-channels', type=int, default=1, help='Number of audio channels.')
    parser.add_argument('--audio-duration', type=int, default=100, help='Audio chunk duration in ms.')

    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Start capture threads
    if args.camera_type == 'rpi':
        args.message = args.message if args.message != 'Camera Stream' else 'RPi Camera'
        video_thread = Thread(target=rpi_video_capture_thread, args=(video_buffer, args), daemon=True)
        video_thread.start()
    elif args.camera_type == 'usb':
        args.message = args.message if args.message != 'Camera Stream' else 'USB Camera'
        video_thread = Thread(target=usb_video_capture_thread, args=(video_buffer, args), daemon=True)
        video_thread.start()

    if args.enable_audio:
        if SOUNDDEVICE_AVAILABLE:
            audio_thread = Thread(target=audio_capture_thread, args=(audio_buffer, args), daemon=True)
            audio_thread.start()
        else:
            logging.warning("Audio libraries not found, audio streaming disabled.")

    # Get local IP address for display
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            myip = s.getsockname()[0]
    except OSError:
        myip = '127.0.0.1'

    logging.info(f"Server starting on http://{myip}:{args.port}")
    if args.enable_audio and SOUNDDEVICE_AVAILABLE:
        logging.info("Audio streaming is enabled on /audio_feed")

    # Run Flask app
    app.run(host=args.host, port=args.port, threaded=True)