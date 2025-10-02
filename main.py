import io
import sys
import argparse
import time
import logging
from threading import Condition, Thread, Lock
from datetime import datetime
import socket
import struct

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

# --- Global Shared State ---
current_audio_level = {'value': 0.0, 'lock': Lock()}

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

    # Draw audio level indicator
    if audio_level > 0:
        # Normalize RMS (typically 0.0 to 1.0) to a bar height
        # Max bar height 100 pixels, adjust scaling factor as needed for microphone sensitivity
        bar_height = int(audio_level * 200) # Scale RMS to a visible bar
        if bar_height > 100: bar_height = 100 # Cap max height
        
        bar_x = 10
        bar_y_bottom = frame.shape[0] - 20
        bar_y_top = bar_y_bottom - bar_height
        bar_width = 20
        
        cv2.rectangle(frame, (bar_x, bar_y_bottom), (bar_x + bar_width, bar_y_top), (0, 255, 0), -1) # Green bar
        cv2.putText(frame, f"{audio_level:.2f}", (bar_x, bar_y_top - 5), font, 0.5, (255, 255, 255), 1) # RMS value

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
    
    class JpegOutput(io.BufferedIOBase):
        def write(self, b):
            buffer.write(b)

    output = JpegOutput()

    def pre_callback(request):
        with MappedArray(request, "main") as m:
            with current_audio_level['lock']:
                level = current_audio_level['value']
            draw_overlay(m.array, args.message, audio_level=level)

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

        with current_audio_level['lock']:
            level = current_audio_level['value']
        draw_overlay(frame, args.message, audio_level=level)

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

    # Log which device is being used
    try:
        if args.audio_device is not None:
            logging.info(f"Attempting to use specified audio device: '{args.audio_device}'")
        else:
            # Query and log the default device
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
    blocksize = int(samplerate * args.audio_duration / 1000) # blocksize in samples

    logging.info(f"Audio stream started with samplerate={samplerate}, channels={channels}.")
    
    try:
        def callback(indata, frames, time, status):
            if status:
                logging.warning(status)
            
            # Calculate RMS audio level
            rms = np.sqrt(np.mean(indata**2)) if indata.size > 0 else 0.0
            with current_audio_level['lock']:
                current_audio_level['value'] = rms

            # Put raw PCM data into the buffer
            buffer.write(indata.tobytes())

        with sd.InputStream(
            device=args.audio_device,
            samplerate=samplerate,
            channels=channels,
            blocksize=blocksize,
            callback=callback
        ):
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
                <audio autoplay>
                    <source src="{{ url_for('audio_feed') }}" type="audio/wav">
                    Your browser does not support the audio element.
                </audio>
            {% endif %}
        </body>
        </html>
    ''', message=args.message, width=args.width, height=args.height, use_audio=use_audio)

def _generate_wav_header(samplerate, channels):
    # Based on WAV file format specification
    # RIFF chunk
    chunk_id = b'RIFF'
    chunk_size = 0xFFFFFFFF  # Placeholder for unknown size (streaming)
    format = b'WAVE'

    # fmt sub-chunk
    subchunk1_id = b'fmt '
    subchunk1_size = 16  # For PCM
    audio_format = 1  # PCM
    num_channels = channels
    sample_rate = samplerate
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8

    # data sub-chunk
    subchunk2_id = b'data'
    subchunk2_size = 0xFFFFFFFF  # Placeholder for unknown size (streaming)

    header = struct.pack('<4sI4s', chunk_id, chunk_size, format)
    header += struct.pack('<4sIHHIIHH', subchunk1_id, subchunk1_size, audio_format, num_channels,
                          sample_rate, byte_rate, block_align, bits_per_sample)
    header += struct.pack('<4sI', subchunk2_id, subchunk2_size)
    return header

def gen_video():
    while True:
        frame = video_buffer.read()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

def gen_audio(args):
    # Generate WAV header once
    wav_header = _generate_wav_header(args.audio_samplerate, args.audio_channels)
    yield wav_header

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
    return Response(gen_audio(args), mimetype='audio/wav')


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
    parser.add_argument('--audio-device', type=str, default=None, help='Audio input device name or index. Use "list" to see available devices.')
    parser.add_argument('--audio-samplerate', type=int, default=44100, help='Audio sample rate in Hz.')
    parser.add_argument('--audio-channels', type=int, default=1, help='Number of audio channels.')
    parser.add_argument('--audio-duration', type=int, default=100, help='Audio chunk duration in ms.')

    args = parser.parse_args()

    # Handle --audio-device list
    if args.audio_device == 'list':
        if not SOUNDDEVICE_AVAILABLE:
            print("Error: sounddevice library is not available. Cannot list audio devices.")
            sys.exit(1)
        print("Available audio input devices:")
        try:
            devices = sd.query_devices()
            found = False
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    print(f"  {i}: {device['name']}")
                    found = True
            if not found:
                print("  No audio input devices found.")
        except Exception as e:
            print(f"  Error querying devices: {e}")
        sys.exit(0)
    
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
