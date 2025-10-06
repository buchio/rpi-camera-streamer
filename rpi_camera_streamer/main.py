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

# --- Global State ---
# This dictionary will hold information about each connected client
# { client_id: {'queue': threading.Queue, 'thread': threading.Thread} }
clients = {}
clients_lock = Lock()

# --- Client-specific Sender Thread ---


def client_sender_thread(ws, client_queue):
    """
    This thread belongs to a single client and is responsible for sending
    messages from its dedicated queue to the WebSocket client.
    """
    while True:
        try:
            # Wait for a message, with a timeout to check if the client is still alive
            message = client_queue.get(timeout=1)
            if message is None:  # None is the signal to terminate
                break
            ws.send(message)
        except queue.Empty:
            # Timeout occurred, which is normal. The loop continues.
            # The 'ws.send()' will raise an exception if the socket is truly closed.
            pass
        except Exception as e:
            logging.warning(
                f"Error sending to client: {e}. Terminating sender thread.")
            break
    logging.info("Client sender thread terminated.")

# --- Broadcaster Thread ---


def broadcast_thread(video_queue, audio_queue):
    """
    This thread fetches data from the video and audio (multiprocessing) queues,
    formats the message, and puts it into the dedicated queue for each client.
    """
    logging.info("Broadcast thread started.")
    queues = [audio_queue, video_queue]  # Audio queue has priority

    # Monitoring variables
    last_log_time = time.time()
    jpeg_size_sum = 0
    jpeg_count = 0

    while True:
        # Non-blocking check on the capture queues
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
                        # Put the formatted message into each client's personal queue
                        with clients_lock:
                            for client_id, client_info in list(clients.items()):
                                try:
                                    client_info['queue'].put_nowait(message)
                                except queue.Full:
                                    logging.warning(
                                        f"Client queue full for {client_id}. Client might be lagging.")
                except queue.Empty:
                    continue

        # Log queue status periodically
        current_time = time.time()
        if current_time - last_log_time > 10:
            avg_jpeg_size_kb = (jpeg_size_sum / jpeg_count /
                                1024) if jpeg_count > 0 else 0
            # Note: qsize() is approximate.
            logging.info(
                f"Broadcast Queues: video={video_queue.qsize()}, audio={audio_queue.qsize()}. "
                f"Avg JPEG Size (10s): {avg_jpeg_size_kb:.1f} KB"
            )
            # Reset counters
            last_log_time = current_time
            jpeg_size_sum = 0
            jpeg_count = 0

        # Sleep briefly if both capture queues are empty
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
                        default=50, help="Internal queue size for video frames.")
    parser.add_argument('--audio-queue-size', type=int, default=500,
                        help="Internal queue size for audio packets.")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)s] %(message)s')

    # --- Initialize Queues ---
    # These are multiprocessing queues to get data from capture processes
    video_queue = Queue(maxsize=args.video_queue_size)
    audio_queue = Queue(maxsize=args.audio_queue_size)

    # --- Web App Initialization and Routes ---
    app = Flask(__name__)
    sock = Sock(app)

    @sock.route('/stream')
    def stream(ws):
        client_id = id(ws)
        # Standard threading queue for this client
        client_queue = queue.Queue(maxsize=100)

        sender_thread = Thread(
            target=client_sender_thread, args=(ws, client_queue))
        sender_thread.daemon = True

        with clients_lock:
            clients[client_id] = {
                'queue': client_queue, 'thread': sender_thread}

        logging.info(f"New client connected: {client_id}")
        sender_thread.start()

        try:
            # This loop will be broken when the client disconnects,
            # causing ws.receive() to raise an exception.
            while True:
                ws.receive()
        except Exception as e:
            logging.info(f"Client {client_id} connection closed or error: {e}")
        finally:
            logging.info(f"Client {client_id} disconnected.")
            with clients_lock:
                if client_id in clients:
                    # Signal the sender thread to terminate
                    try:
                        clients[client_id]['queue'].put_nowait(None)
                    except queue.Full:
                        pass  # If queue is full, thread will eventually timeout and exit
                    del clients[client_id]

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
    # This thread now fans out messages to individual client queues
    broadcaster = Thread(target=broadcast_thread, args=(
        video_queue, audio_queue), daemon=True)
    broadcaster.start()

    logging.info(f"Server starting on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == '__main__':
    main()
