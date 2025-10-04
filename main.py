import io
import sys
import argparse
import time
import logging
import threading
import multiprocessing
from threading import Thread, Lock
from datetime import datetime
import socket
import struct
import queue

import cv2
import numpy as np
from flask import Flask, Response, render_template_string, request

# --- Conditional Imports ---
try:
    from picamera2 import Picamera2, MappedArray
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    SOUNDDEVICE_AVAILABLE = False

try:
    from flask_cors import CORS
    FLASK_CORS_AVAILABLE = True
except ImportError:
    FLASK_CORS_AVAILABLE = False

# --- Thread-local data for logging ---
local = threading.local()

class ServerNameFilter(logging.Filter):
    def filter(self, record):
        record.server_name = getattr(local, 'server_name', 'main')
        return True

# --- Global Shared State ---
current_audio_level = {'value': 0.0, 'lock': Lock()}

# --- Core Functions ---
def draw_overlay(frame, message=None, audio_level=0.0):
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

    if audio_level > 0:
        bar_height = int(audio_level * 200)
        if bar_height > 100: bar_height = 100
        bar_x = 10
        bar_y_bottom = frame.shape[0] - 20
        bar_y_top = bar_y_bottom - bar_height
        bar_width = 20
        cv2.rectangle(frame, (bar_x, bar_y_bottom), (bar_x + bar_width, bar_y_top), (0, 255, 0), -1)
        cv2.putText(frame, f"{audio_level:.2f}", (bar_x, bar_y_top - 5), font, 0.5, (255, 255, 255), 1)

# --- Capture Threads / Processes ---
def rpi_video_capture_thread(buffer, args):
    local.server_name = 'VID_CAP'
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
    
    class JpegOutput(io.BufferedIOBase):
        def write(self, b):
            buffer.put(b)

    output = JpegOutput()
    def pre_callback(request):
        with MappedArray(request, "main") as m:
            with current_audio_level['lock']:
                level = current_audio_level['value']
            draw_overlay(m.array, args.message, audio_level=level)
    
    picam2.pre_callback = pre_callback
    picam2.start_recording(encoder, FileOutput(output))
    logging.info("RPi camera hardware encoding started.")
    try:
        while True: time.sleep(1)
    finally:
        picam2.stop_recording()

def usb_video_capture_thread(raw_frame_queue, args):
    local.server_name = 'VID_CAP'
    cap = cv2.VideoCapture(args.device_id, cv2.CAP_V4L2)
    if not cap.isOpened():
        logging.error(f"Could not open camera device ID {args.device_id}.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    logging.info("USB camera capture started.")
    seq = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            logging.warning("Could not read frame from USB camera.")
            continue
        # Put frame and sequence number in the queue
        raw_frame_queue.put((seq, frame))
        seq += 1

def jpeg_encoder_process(in_q, out_q, args):
    local.server_name = 'JPEG_ENC'
    logging.info("JPEG encoder process started.")
    while True:
        seq, frame = in_q.get()
        if frame is None: break

        with current_audio_level['lock']:
            level = current_audio_level['value']
        draw_overlay(frame, args.message, audio_level=level)
        
        ret, encoded_frame = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])
        if ret:
            # Put sequence number and encoded frame in the output queue
            out_q.put((seq, encoded_frame.tobytes()))

def audio_capture_thread(buffer, args):
    local.server_name = 'AUD_CAP'
    if not SOUNDDEVICE_AVAILABLE:
        logging.error("sounddevice library is not available. Audio streaming is disabled.")
        return
    try:
        if args.audio_device is not None:
            logging.info(f"Attempting to use specified audio device: '{args.audio_device}'")
        else:
            device_index = sd.default.device[0]
            if device_index == -1:
                logging.error("No default audio input device found.")
                return
            device_name = sd.query_devices(device_index)['name']
            logging.info(f"Using default audio input device: {device_name}")
    except Exception as e:
        logging.error(f"Error querying audio devices: {e}")
        return

    samplerate = args.audio_samplerate
    channels = args.audio_channels
    blocksize = 0
    logging.info(f"Audio stream started with samplerate={samplerate}, channels={channels}.")
    try:
        def callback(indata, frames, time, status):
            if status: logging.warning(status)
            rms = np.sqrt(np.mean(indata.astype(np.float32)**2)) if indata.size > 0 else 0.0
            normalized_rms = rms / 32768.0
            with current_audio_level['lock']:
                current_audio_level['value'] = normalized_rms
            if args.audio_noise_gate > 0 and normalized_rms < args.audio_noise_gate:
                buffer.put(np.zeros_like(indata).tobytes())
            else:
                buffer.put(indata.tobytes())
        with sd.InputStream(device=args.audio_device, samplerate=samplerate, channels=channels, blocksize=blocksize, dtype='int16', callback=callback):
            while True: time.sleep(10)
    except Exception as e:
        logging.error(f"Audio capture failed: {e}")

# --- Main Execution ---
if __name__ == '__main__':
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Multi-process camera streamer for Raspberry Pi.")
    parser.add_argument('--camera-type', type=str, required=True, choices=['rpi', 'usb'], help='Type of camera to use.')
    parser.add_argument('--port', type=int, default=8080, help='Port for the web server (video).')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host address for the web server.')
    parser.add_argument('--message', type=str, default='Camera Stream', help='Message to display on stream.')
    parser.add_argument('--width', type=int, default=640, help='Frame width.')
    parser.add_argument('--height', type=int, default=480, help='Frame height.')
    parser.add_argument('--fps', type=int, default=15, help='Frames per second.')
    parser.add_argument('--quality', type=int, default=70, help='JPEG quality (1-100).')
    parser.add_argument('--device-id', type=int, default=0, help='USB camera device ID.')
    parser.add_argument('--enable-audio', action='store_true', help='Enable audio streaming.')
    parser.add_argument('--audio-port', type=int, default=8081, help='Port for the audio server.')
    parser.add_argument('--audio-device', type=str, default=None, help='Audio input device name or index. Use "list" to see available devices.')
    parser.add_argument('--audio-samplerate', type=int, default=44100, help='Audio sample rate in Hz.')
    parser.add_argument('--audio-channels', type=int, default=1, help='Number of audio channels.')
    parser.add_argument('--audio-duration', type=int, default=100, help='Audio chunk duration in ms.')
    parser.add_argument('--audio-noise-gate', type=float, default=0.0, help='Noise gate threshold (0.0-1.0). Suppresses audio below this volume. Default is 0.0 (disabled).')
    args = parser.parse_args()

    # --- Custom Logging Setup ---
    root_logger = logging.getLogger()
    if root_logger.hasHandlers(): root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(server_name)-8s] %(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    handler.addFilter(ServerNameFilter())
    root_logger.addHandler(handler)
    local.server_name = 'main'

    if args.audio_device == 'list':
        if not SOUNDDEVICE_AVAILABLE: sys.exit("Error: sounddevice library is not available.")
        print("Available audio input devices:")
        try:
            for i, device in enumerate(sd.query_devices()):
                if device['max_input_channels'] > 0: print(f"  {i}: {device['name']}")
        except Exception as e:
            print(f"  Error querying devices: {e}")
        sys.exit(0)

    # --- Buffer Initialization ---
    audio_buffer = queue.Queue()
    if args.camera_type == 'usb':
        video_buffer = multiprocessing.Queue()
        raw_frame_queue = multiprocessing.Queue()
    else: # rpi
        video_buffer = queue.Queue()

    # --- Web App Initialization ---
    video_app = Flask("video_app")
    audio_app = Flask("audio_app")

    # --- Route Definitions (as closures) ---
    @video_app.route('/')
    @video_app.route('/index.html')
    def index():
        use_audio = args.enable_audio and SOUNDDEVICE_AVAILABLE
        audio_url = ""
        if use_audio:
            host = request.host.split(':')[0]
            audio_url = f"http://{host}:{args.audio_port}/audio_feed"
        return render_template_string('''
            <html><head><title>{{ message }}</title></head>
            <body><h1>{{ message }}</h1>
            <img src="{{ url_for('video_feed') }}" width="{{ width }}" height="{{ height }}">
            {% if use_audio %}
                <h2>Audio Stream</h2>
                <audio controls autoplay>
                    <source src="{{ audio_url }}" type="audio/wav">
                    Your browser does not support the audio element.
                </audio>
            {% endif %}</body></html>
        ''', message=args.message, width=args.width, height=args.height, use_audio=use_audio, audio_url=audio_url)

    def gen_video_ordered():
        frame_buffer = {}
        next_frame_num = 0
        while True:
            seq, jpeg_data = video_buffer.get()
            frame_buffer[seq] = jpeg_data
            while next_frame_num in frame_buffer:
                frame_to_yield = frame_buffer.pop(next_frame_num)
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_to_yield + b'\r\n')
                next_frame_num += 1

    def gen_video_simple():
        while True: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + video_buffer.get() + b'\r\n')

    @video_app.route('/video_feed')
    def video_feed(): 
        if args.camera_type == 'usb':
            return Response(gen_video_ordered(), mimetype='multipart/x-mixed-replace; boundary=frame')
        else: # rpi
            return Response(gen_video_simple(), mimetype='multipart/x-mixed-replace; boundary=frame')

    def _generate_wav_header(samplerate, channels):
        chunk_id, chunk_size, format = b'RIFF', 0xFFFFFFFF, b'WAVE'
        subchunk1_id, subchunk1_size, audio_format = b'fmt ', 16, 1
        num_channels, sample_rate = channels, samplerate
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        subchunk2_id, subchunk2_size = b'data', 0xFFFFFFFF
        header = struct.pack('<4sI4s', chunk_id, chunk_size, format)
        header += struct.pack('<4sIHHIIHH', subchunk1_id, subchunk1_size, audio_format, num_channels, sample_rate, byte_rate, block_align, bits_per_sample)
        header += struct.pack('<4sI', subchunk2_id, subchunk2_size)
        return header
    def gen_audio():
        yield _generate_wav_header(args.audio_samplerate, args.audio_channels)
        while True: yield audio_buffer.get()
    @audio_app.route('/audio_feed')
    def audio_feed(): 
        if not args.enable_audio: return "Audio not enabled", 404
        return Response(gen_audio(), mimetype='audio/wav')

    # --- Start Capture Threads / Processes ---
    if args.camera_type == 'rpi':
        video_thread = Thread(target=rpi_video_capture_thread, args=(video_buffer, args), daemon=True)
        video_thread.start()
    elif args.camera_type == 'usb':
        video_thread = Thread(target=usb_video_capture_thread, args=(raw_frame_queue, args), daemon=True)
        video_thread.start()
        num_encoders = multiprocessing.cpu_count() - 1 if multiprocessing.cpu_count() > 1 else 1
        for _ in range(num_encoders):
            encoder_proc = multiprocessing.Process(target=jpeg_encoder_process, args=(raw_frame_queue, video_buffer, args), daemon=True)
            encoder_proc.start()
        logging.info(f"Started {num_encoders} JPEG encoder process(es).")

    if args.enable_audio:
        if not SOUNDDEVICE_AVAILABLE: logging.warning("Audio libraries not found, audio streaming disabled.")
        else:
            if not FLASK_CORS_AVAILABLE: sys.exit("Error: Flask-Cors is not installed. Please run 'pip install Flask-Cors'")
            audio_capture_thread = Thread(target=audio_capture_thread, args=(audio_buffer, args), daemon=True)
            audio_capture_thread.start()
            def run_audio_app():
                local.server_name = 'AUDIO'
                CORS(audio_app)
                logging.info(f"Server starting on port {args.audio_port}")
                audio_app.run(host=args.host, port=args.audio_port, threaded=True)
            audio_server_thread = Thread(target=run_audio_app, daemon=True)
            audio_server_thread.start()

    # --- Start Video Web Server ---
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            myip = s.getsockname()[0]
    except OSError:
        myip = '127.0.0.1'

    local.server_name = 'VIDEO'
    logging.info(f"Server starting on http://{myip}:{args.port}")
    video_app.run(host=args.host, port=args.port, threaded=True)