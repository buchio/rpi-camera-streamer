
import io
import time
import logging
import cv2

try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False


def add_video_args(parser):
    parser.add_argument('--camera-type', type=str,
                        required=True, choices=['rpi', 'usb'])
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--fps', type=int, default=15)
    parser.add_argument('--quality', type=int, default=70)
    parser.add_argument('--device-id', type=int, default=0)


def video_capture_process(args, video_queue):
    logging.info(f"Starting video capture with type: {args.camera_type}")
    if args.camera_type == 'rpi':
        if not PICAMERA2_AVAILABLE:
            logging.error(
                "picamera2 library not found. Raspberry Pi camera stream will not start.")
            return
        picam2 = Picamera2()
        video_config = picam2.create_video_configuration(main={"format": "XBGR8888", "size": (
            args.width, args.height)}, controls={"FrameRate": args.fps})
        picam2.configure(video_config)

        # Get the actual resolution from the camera configuration
        actual_config = picam2.camera_configuration()
        actual_width = actual_config['main']['size'][0]
        actual_height = actual_config['main']['size'][1]
        logging.info(
            f"RPi camera configured to: {actual_width}x{actual_height}")

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
                if not video_queue.full():
                    video_queue.put(
                        ('video', timestamp, actual_width, actual_height, frame_data))
                else:
                    logging.warning(
                        "Video queue full, dropping video frame.")
        finally:
            picam2.stop_recording()

    elif args.camera_type == 'usb':
        cap = cv2.VideoCapture(args.device_id, cv2.CAP_V4L2)
        if not cap.isOpened():
            return logging.error(f"Could not open camera device ID {args.device_id}.")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FPS, args.fps)
        wait_time = 1.0 / args.fps
        while True:
            start_time = time.time()
            ret, frame = cap.read()
            timestamp = time.time()
            if not ret:
                continue
            ret, encoded_frame = cv2.imencode(
                '.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])
            if ret:
                if not video_queue.full():
                    video_queue.put(
                        ('video', timestamp, frame.shape[1], frame.shape[0], encoded_frame.tobytes()))
                else:
                    logging.warning(
                        "Video queue full, dropping video frame.")
            elapsed = time.time() - start_time
            if wait_time > elapsed:
                time.sleep(wait_time - elapsed)
