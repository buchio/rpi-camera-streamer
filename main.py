import io
import sys
import argparse
import time
import logging
import threading
import base64
from threading import Thread, Lock
from datetime import datetime
import socket
import struct
import queue

import cv2
import numpy as np
from flask import Flask, render_template_string

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
    from flask_sock import Sock
    FLASK_SOCK_AVAILABLE = True
except ImportError:
    FLASK_SOCK_AVAILABLE = False

# --- Global State & Queues ---
clients = []
clients_lock = Lock()
combined_queue = queue.Queue(maxsize=100)

# --- Capture Threads ---
def video_capture_thread(args):
    logging.info(f"Starting video capture with type: {args.camera_type}")
    if args.camera_type == 'rpi':
        if not PICAMERA2_AVAILABLE: return logging.error("picamera2 library not found.")
        picam2 = Picamera2()
        video_config = picam2.create_video_configuration(main={"format": "XBGR8888", "size": (args.width, args.height)}, controls={"FrameRate": args.fps})
        picam2.configure(video_config)
        encoder = JpegEncoder(q=args.quality)
        output = io.BytesIO()
        picam2.start_recording(encoder, FileOutput(output))
        try:
            while True:
                picam2.wait_recording(1)
                timestamp = time.time()
                frame_data = output.getvalue()
                output.seek(0)
                output.truncate()
                if not combined_queue.full():
                    combined_queue.put(('video', timestamp, frame_data))
                else:
                    logging.warning("Combined queue full, dropping video frame.")
        finally:
            picam2.stop_recording()
    
    elif args.camera_type == 'usb':
        cap = cv2.VideoCapture(args.device_id, cv2.CAP_V4L2)
        if not cap.isOpened(): return logging.error(f"Could not open camera device ID {args.device_id}.")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FPS, args.fps)
        wait_time = 1.0 / args.fps
        while True:
            start_time = time.time()
            ret, frame = cap.read()
            timestamp = time.time()
            if not ret: continue
            ret, encoded_frame = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])
            if ret:
                if not combined_queue.full():
                    combined_queue.put(('video', timestamp, encoded_frame.tobytes()))
                else:
                    logging.warning("Combined queue full, dropping video frame.")
            elapsed = time.time() - start_time
            if wait_time > elapsed: time.sleep(wait_time - elapsed)

def audio_capture_thread(args):
    if not SOUNDDEVICE_AVAILABLE: return logging.error("sounddevice library not found.")
    try:
        device_info = sd.query_devices(args.audio_device, 'input')
        if args.audio_samplerate is None:
            samplerate = int(device_info['default_samplerate'])
            logging.info(f"Using default sample rate: {samplerate} Hz")
        else:
            samplerate = args.audio_samplerate
            logging.info(f"Using specified sample rate: {samplerate} Hz")
        channels = args.audio_channels
        blocksize = 2048 # Use a moderate, fixed block size
        logging.info(f"Using audio device: {device_info['name']} with blocksize {blocksize}")
    except Exception as e:
        return logging.error(f"Error querying audio devices: {e}")

    def callback(indata, frames, time_info, status):
        if status: logging.warning(status)
        timestamp = time.time()
        if not combined_queue.full():
            combined_queue.put(('audio', timestamp, indata.tobytes()))
        else:
            logging.warning("Combined queue full, dropping audio frame.")

    with sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=blocksize, callback=callback):
        while True: time.sleep(10)

def broadcaster_thread():
    logging.info("Broadcaster thread started.")
    while True:
        event_type, timestamp, data = combined_queue.get()
        with clients_lock:
            disconnected_clients = []
            message = f'{event_type}:{timestamp}:{base64.b64encode(data).decode("utf-8")}'
            for client in clients:
                try:
                    client.send(message)
                except Exception as e:
                    disconnected_clients.append(client)
                    logging.info(f"Client disconnected: {e}")
            for client in disconnected_clients:
                clients.remove(client)

# --- Main Execution ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="WebSocket Media Streamer")
    parser.add_argument('--camera-type', type=str, required=True, choices=['rpi', 'usb'])
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--host', type=str, default='0.0.0.0')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--fps', type=int, default=15)
    parser.add_argument('--quality', type=int, default=70)
    parser.add_argument('--device-id', type=int, default=0)
    parser.add_argument('--enable-audio', action='store_true')
    parser.add_argument('--audio-device', type=int, default=None)
    parser.add_argument('--audio-channels', type=int, default=1, help="Number of audio channels (1=mono).")
    parser.add_argument('--audio-samplerate', type=int, default=None, help="Audio sample rate in Hz. Defaults to device default.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

    if not FLASK_SOCK_AVAILABLE:
        sys.exit("Error: Flask-Sock is not installed. Please run 'pip install Flask-Sock'")

    # --- Web App Initialization and Routes ---
    app = Flask(__name__)
    sock = Sock(app)

    @app.route('/')
    @app.route('/index.html')
    def index():
        if args.audio_samplerate:
            display_samplerate = args.audio_samplerate
        else:
            try:
                device_info = sd.query_devices(args.audio_device, 'input')
                display_samplerate = int(device_info['default_samplerate'])
            except:
                display_samplerate = 44100
        return render_template_string('''
<html>
<head>
    <title>WebSocket Media Stream</title>
    <style>
        body { font-family: sans-serif; display: flex; flex-direction: column; align-items: center; background: #222; color: #eee; }
        #video-container { position: relative; }
        #video { background: #000; min-width: 640px; min-height: 480px; border: 1px solid #444; }
        #overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); color: white; display: flex; justify-content: center; align-items: center; cursor: pointer; font-size: 1.5em; }
        #log { width: 640px; height: 200px; overflow-y: scroll; border: 1px solid #444; background: #333; padding: 5px; font-family: monospace; }
    </style>
</head>
<body>
    <h1>WebSocket Media Stream</h1>
    <div id="video-container">
        <img id="video" src="" width="{{width}}" height="{{height}}">
        <div id="overlay">Click to Start Audio</div>
    </div>
    <h3>Log</h3>
    <div id="log"></div>
    <script>
        const video = document.getElementById('video');
        const logDiv = document.getElementById('log');
        const overlay = document.getElementById('overlay');
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: {{ samplerate }} });
        
        function log(message) {
            const p = document.createElement('p');
            p.innerText = `[${new Date().toLocaleTimeString()}] ${message}`;
            logDiv.appendChild(p);
            logDiv.scrollTop = logDiv.scrollHeight;
        }

        let audioQueue = [];
        let nextPlayTime = 0;
        let isPlaying = false;
        const scheduleAheadTime = 0.2;

        function schedulePlayback() {
            while (audioQueue.length > 0 && nextPlayTime < audioCtx.currentTime + scheduleAheadTime) {
                const audioBuffer = audioQueue.shift();
                const source = audioCtx.createBufferSource();
                source.buffer = audioBuffer;
                source.connect(audioCtx.destination);

                if (nextPlayTime < audioCtx.currentTime) {
                    nextPlayTime = audioCtx.currentTime;
                }

                source.start(nextPlayTime);
                nextPlayTime += audioBuffer.duration;
            }
        }

        function initializeAudio() {
            const startPlaybackLoop = () => {
                if (!isPlaying) {
                    isPlaying = true;
                    setInterval(schedulePlayback, 50);
                    log('Audio playback scheduler started.');
                }
            };

            if (audioCtx.state === 'suspended') {
                audioCtx.resume().then(() => {
                    log('Audio context resumed.');
                    startPlaybackLoop();
                }).catch(e => log(`Audio context resume failed: ${e}`));
            } else {
                startPlaybackLoop();
            }
            overlay.style.display = 'none';
        }
        overlay.addEventListener('click', initializeAudio, { once: true });

        const socket = new WebSocket(`ws://${window.location.host}/stream`);

        socket.onopen = () => log('WebSocket connection established.');
        socket.onclose = () => log('WebSocket connection closed.');
        socket.onerror = (err) => log(`WebSocket error: ${err}`);

        socket.onmessage = (event) => {
            const parts = event.data.split(':');
            const type = parts[0];
            const timestamp = parseFloat(parts[1]);
            const data = parts[2];

            if (type === 'video') {
                video.src = 'data:image/jpeg;base64,' + data;
            } else if (type === 'audio') {
                const binaryString = atob(data);
                const len = binaryString.length;
                const bytes = new Uint8Array(len);
                for (let i = 0; i < len; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }

                // Use DataView for robust little-endian decoding
                const dataView = new DataView(bytes.buffer);
                const float32Array = new Float32Array(len / 2);
                for (let i = 0; i < float32Array.length; i++) {
                    // (byteOffset, littleEndian)
                    const int16 = dataView.getInt16(i * 2, true); 
                    float32Array[i] = int16 / 32768.0;
                }

                const audioBuffer = audioCtx.createBuffer(1, float32Array.length, audioCtx.sampleRate);
                audioBuffer.copyToChannel(float32Array, 0);
                audioQueue.push(audioBuffer);
            }
        };

        log('Client initialized.');
    </script>
</body>
</html>
        ''', width=args.width, height=args.height, samplerate=display_samplerate)

    @sock.route('/stream')
    def stream(ws):
        log_msg = f"New client connected: {ws.environ.get('REMOTE_ADDR')}"
        logging.info(log_msg)
        with clients_lock:
            clients.append(ws)
        try:
            while True:
                ws.receive()
        except Exception as e:
            logging.info(f"Connection closed for {ws.environ.get('REMOTE_ADDR')}: {e}")
        finally:
            with clients_lock:
                if ws in clients:
                    clients.remove(ws)

    # --- Start background threads ---
    Thread(target=video_capture_thread, args=(args,), daemon=True).start()
    if args.enable_audio:
        Thread(target=audio_capture_thread, args=(args,), daemon=True).start()
    Thread(target=broadcaster_thread, daemon=True).start()

    logging.info(f"Server starting on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)