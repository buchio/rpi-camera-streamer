import sys
import argparse
import time
import logging
import base64
import queue
from multiprocessing import Process, Queue
from threading import Thread, Lock

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

import queue

# --- Global State & Queues ---
clients = []
clients_lock = Lock()

# --- Broadcaster Thread ---


def broadcast_thread(video_queue, audio_queue, video_queue_maxsize, audio_queue_maxsize):
    logging.info("Broadcast thread started.")
    queues = [audio_queue, video_queue]  # Audio queue has priority

    # Monitoring variables
    last_log_time = time.time()
    jpeg_size_sum = 0
    jpeg_count = 0

    while True:
        disconnected_clients = set()
        for q in queues:
            if not q.empty():
                try:
                    item = q.get_nowait()
                    event_type = item[0]
                    message = ""

                    if event_type == 'video':
                        _, timestamp, width, height, raw_size, data = item
                        jpeg_size_sum += raw_size
                        jpeg_count += 1
                        message = f'video:{timestamp}:{width}:{height}:{data.decode("utf-8")}'
                    elif event_type == 'audio':
                        _, timestamp, data = item
                        message = f'audio:{timestamp}:{data.decode("utf-8")}'

                    if message:
                        with clients_lock:
                            for client in clients:
                                try:
                                    client.send(message)
                                except Exception:
                                    disconnected_clients.add(client)
                except queue.Empty:
                    continue

        if disconnected_clients:
            with clients_lock:
                for client in disconnected_clients:
                    if client in clients:
                        clients.remove(client)
                        logging.info("Client disconnected and removed.")

        # --- Log queue status periodically --- #
        current_time = time.time()
        if current_time - last_log_time > 10:
            avg_jpeg_size_kb = (jpeg_size_sum / jpeg_count /
                                1024) if jpeg_count > 0 else 0
            logging.info(
                f"Queue Status: video={video_queue.qsize()}/{video_queue_maxsize}, "
                f"audio={audio_queue.qsize()}/{audio_queue_maxsize}, "
                f"avg_jpeg_kb={avg_jpeg_size_kb:.1f}"
            )
            # Reset counters
            last_log_time = current_time
            jpeg_size_sum = 0
            jpeg_count = 0
        # ------------------------------------ #

        # Sleep briefly if both queues are empty to prevent busy-waiting
        if audio_queue.empty() and video_queue.empty():
            time.sleep(0.001)

# --- Main Execution ---


def main():
    parser = argparse.ArgumentParser(description="WebSocket Media Streamer")

    if video:
        video.add_video_args(parser)

    if audio:
        audio.add_audio_args(parser)

    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--host', type=str, default='0.0.0.0')
    parser.add_argument('--video-queue-size', type=int,
                        default=10, help="Internal queue size for video frames.")
    parser.add_argument('--audio-queue-size', type=int, default=50,
                        help="Internal queue size for audio packets.")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)s] %(message)s')

    # --- Initialize Queues ---
    video_queue = Queue(maxsize=args.video_queue_size)
    audio_queue = Queue(maxsize=args.audio_queue_size)

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

    # --- Start background processes and threads ---
    if video:
        Process(target=video.video_capture_process, args=(
            args, video_queue), daemon=True).start()
    else:
        logging.error(
            "Video module not available. Video components not started.")

    if args.enable_audio:
        if audio:
            Process(target=audio.audio_capture_process, args=(
                args, audio_queue), daemon=True).start()
        else:
            logging.warning(
                "Audio module not available. Audio components not started.")

    # Start the unified broadcaster thread
    Thread(target=broadcast_thread, args=(
        video_queue, audio_queue, args.video_queue_size, args.audio_queue_size), daemon=True).start()

    logging.info(f"Server starting on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == '__main__':
    main()
