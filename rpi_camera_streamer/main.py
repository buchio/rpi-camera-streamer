import sys
import argparse
import time
import logging
import struct
import queue
import asyncio
from multiprocessing import Process, Queue

from quart import Quart, websocket

# --- Conditional Imports & Module Availability ---
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
# { client_id: asyncio.Queue }
clients = {}
clients_lock = asyncio.Lock()

# --- Client-specific Sender Task ---


async def client_sender_task(ws, client_queue):
    """This asyncio task sends messages from a client's dedicated queue."""
    while True:
        try:
            message = await client_queue.get()
            if message is None:  # Termination signal
                break
            await ws.send(message)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.warning(f"Error in sender task: {e}. Terminating.")
            break
    logging.info("Client sender task terminated.")

# --- Broadcaster Task ---


async def broadcast_task(video_queue, audio_queue):
    """Fetches data from capture processes and fans it out to clients."""
    logging.info("Broadcast task started.")
    queues = [audio_queue, video_queue]  # Audio queue has priority

    # Monitoring variables
    last_log_time = time.time()
    jpeg_size_sum = 0
    jpeg_count = 0

    while True:
        for q in queues:
            if not q.empty():
                try:
                    item = q.get_nowait()
                    event_type = item[0]
                    message = b''  # Message is now bytes

                    if event_type == 'video':
                        # item: ('video', timestamp, width, height, data)
                        _, timestamp, width, height, data = item
                        jpeg_size_sum += len(data)
                        jpeg_count += 1
                        # Pack as: 'v' (1 byte) + timestamp (8 bytes, double) + width (2 bytes, short) + height (2 bytes, short) + jpeg_data
                        message = b'v' + struct.pack('<dHH', timestamp, width, height) + data
                    elif event_type == 'audio':
                        # item: ('audio', timestamp, data)
                        _, timestamp, data = item
                        # Pack as: 'a' (1 byte) + timestamp (8 bytes, double) + audio_data
                        message = b'a' + struct.pack('<d', timestamp) + data

                    if message:
                        async with clients_lock:
                            for client_q in clients.values():
                                try:
                                    client_q.put_nowait(message)
                                except asyncio.QueueFull:
                                    # The queue is full. Drop the oldest frame and add the new one.
                                    try:
                                        client_q.get_nowait()  # Remove the oldest item
                                        client_q.put_nowait(message)  # Add the newest item
                                    except (asyncio.QueueEmpty, asyncio.QueueFull):
                                        # This might happen under race conditions. If so, we just drop the frame.
                                        logging.warning(
                                            "Dropping frame for lagging client under race condition.")
                                        pass
                except queue.Empty:
                    continue

        # Log queue status periodically
        current_time = time.time()
        if current_time - last_log_time > 10:
            avg_jpeg_size_kb = (jpeg_size_sum / jpeg_count /
                                1024) if jpeg_count > 0 else 0
            logging.info(
                f"Broadcast Queues: video={video_queue.qsize()}, audio={audio_queue.qsize()}. "
                f"Avg JPEG Size (10s): {avg_jpeg_size_kb:.1f} KB"
            )
            last_log_time = current_time
            jpeg_size_sum = 0
            jpeg_count = 0

        await asyncio.sleep(0.001)  # Yield control to the event loop

# --- Main Execution ---


async def main():
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

    video_queue = Queue(maxsize=args.video_queue_size)
    audio_queue = Queue(maxsize=args.audio_queue_size)

    app = Quart(__name__)

    @app.websocket('/stream')
    async def stream():
        ws = websocket._get_current_object()
        client_id = id(ws)
        client_queue = asyncio.Queue(maxsize=100)
        sender_task = asyncio.create_task(client_sender_task(ws, client_queue))

        async with clients_lock:
            clients[client_id] = client_queue

        logging.info(f"New client connected: {client_id}")

        try:
            while True:
                await ws.receive()
        except asyncio.CancelledError:
            pass  # Expected on disconnect
        finally:
            logging.info(f"Client {client_id} disconnected.")
            sender_task.cancel()
            async with clients_lock:
                if client_id in clients:
                    del clients[client_id]

    # Start background processes
    if video:
        Process(target=video.video_capture_process, args=(
            args, video_queue), daemon=True).start()
    if args.enable_audio:
        if audio:
            Process(target=audio.audio_capture_process, args=(
                args, audio_queue), daemon=True).start()

    # Start background asyncio tasks
    asyncio.create_task(broadcast_task(video_queue, audio_queue))

    logging.info(f"Server starting on http://{args.host}:{args.port}")
    await app.run_task(host=args.host, port=args.port)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server shutting down.")