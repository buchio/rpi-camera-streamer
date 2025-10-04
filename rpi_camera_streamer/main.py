import sys
import argparse
import time
import logging
import base64
from threading import Thread, Lock
import queue

from flask import Flask

# --- Conditional Imports & Module Availability ---
try:
    from flask_sock import Sock
except ImportError:
    sys.exit("Error: Flask-Sock is not installed. Please run 'pip install Flask-Sock'")

try:
    from .video import video_capture_thread
    VIDEO_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Could not import video module: {e}")
    VIDEO_AVAILABLE = False

try:
    from .audio import audio_capture_thread
    AUDIO_AVAILABLE = True
except (ImportError, OSError) as e:
    logging.warning(f"Could not import audio module: {e}")
    AUDIO_AVAILABLE = False

# --- Global State & Queues ---
clients = []
clients_lock = Lock()
combined_queue = queue.Queue(maxsize=100)

# --- Broadcaster Thread ---


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


def main():
    parser = argparse.ArgumentParser(description="WebSocket Media Streamer")
    parser.add_argument('--camera-type', type=str,
                        required=True, choices=['rpi', 'usb'])
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--host', type=str, default='0.0.0.0')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--fps', type=int, default=15)
    parser.add_argument('--quality', type=int, default=70)
    parser.add_argument('--device-id', type=int, default=0)
    parser.add_argument('--enable-audio', action='store_true')
    parser.add_argument('--audio-device', type=int, default=None)
    parser.add_argument('--audio-channels', type=int, default=1,
                        help="Number of audio channels (1=mono).")
    parser.add_argument('--audio-samplerate', type=int, default=None,
                        help="Audio sample rate in Hz. Defaults to device default.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)s] %(message)s')

    # --- Web App Initialization and Routes ---
    app = Flask(__name__)
    sock = Sock(app)

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
            logging.info(
                f"Connection closed for {ws.environ.get('REMOTE_ADDR')}: {e}")
        finally:
            with clients_lock:
                if ws in clients:
                    clients.remove(ws)

    # --- Start background threads ---
    if VIDEO_AVAILABLE:
        Thread(target=video_capture_thread, args=(
            args, combined_queue), daemon=True).start()
    else:
        logging.error("Video capture thread not started due to import errors.")

    if args.enable_audio:
        if AUDIO_AVAILABLE:
            Thread(target=audio_capture_thread, args=(
                args, combined_queue), daemon=True).start()
        else:
            logging.warning(
                "Audio capture thread not started. Check audio device or library installation.")

    Thread(target=broadcaster_thread, daemon=True).start()

    logging.info(f"Server starting on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == '__main__':
    main()
