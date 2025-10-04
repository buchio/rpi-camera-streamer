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
    from . import video
except ImportError as e:
    logging.warning(f"Could not import video module: {e}")
    video = None

try:
    from . import audio
except (ImportError, OSError) as e:
    logging.warning(f"Could not import audio module: {e}")
    audio = None

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

    if video:
        video.add_video_args(parser)

    if audio:
        audio.add_audio_args(parser)

    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--host', type=str, default='0.0.0.0')

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
    if video:
        Thread(target=video.video_capture_thread, args=(
            args, combined_queue), daemon=True).start()
    else:
        logging.error("Video module not available. Video thread not started.")

    if args.enable_audio:
        if audio:
            Thread(target=audio.audio_capture_thread, args=(
                args, combined_queue), daemon=True).start()
        else:
            logging.warning(
                "Audio module not available. Audio thread not started.")

    Thread(target=broadcaster_thread, daemon=True).start()

    logging.info(f"Server starting on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == '__main__':
    main()
