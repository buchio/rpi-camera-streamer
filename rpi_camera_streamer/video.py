
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


import subprocess
import re


def add_video_args(parser):
    parser.add_argument('--camera-type', type=str,
                        required=True, choices=['rpi', 'usb'])
    # Output arguments
    parser.add_argument('--width', type=int, default=640,
                        help="Final output width.")
    parser.add_argument('--height', type=int, default=480,
                        help="Final output height.")

    # Capture arguments (for USB cameras)
    parser.add_argument('--capture-width', type=int, default=None,
                        help="[USB only] Width for capturing from the camera.")
    parser.add_argument('--capture-height', type=int, default=None,
                        help="[USB only] Height for capturing from the camera.")

    parser.add_argument('--fps', type=int, default=15,
                        help="Frames per second.")
    parser.add_argument('--quality', type=int, default=70,
                        help="JPEG encoding quality (1-100).")
    parser.add_argument('--device-id', type=int, default=0,
                        help="USB camera device ID.")


def _log_rpi_camera_modes():
    "Logs the sensor modes available for a picamera2 device."
    if not PICAMERA2_AVAILABLE:
        return
    try:
        picam2 = Picamera2()
        logging.info("--- RPi Camera Supported Modes ---")
        for mode in picam2.sensor_modes:
            logging.info(mode)
        logging.info("--------------------------------")
        picam2.close()  # Close the camera after getting modes
    except Exception as e:
        logging.warning(f"Could not enumerate RPi camera modes: {e}")


def _log_usb_camera_formats(device_id):
    "Logs supported formats and resolutions for a USB camera using v4l2-ctl."
    device_path = f"/dev/video{device_id}"
    logging.info(
        f"--- USB Camera Supported Formats for {device_path} (via v4l2-ctl) ---")
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--device', device_path, '--list-formats-ext'],
            capture_output=True, text=True, check=True
        )
        output = result.stdout
        # Log the relevant lines for formats and sizes
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('[') or line.startswith('Size: Discrete'):
                logging.info(line)
        logging.info(
            "-----------------------------------------------------------------")
    except FileNotFoundError:
        logging.warning(
            "'v4l2-ctl' command not found. Cannot list USB camera formats.")
    except subprocess.CalledProcessError as e:
        logging.warning(
            f"Error executing 'v4l2-ctl' for {device_path}: {e.stderr.strip()}")
    except Exception as e:
        logging.warning(
            f"An unexpected error occurred while checking USB formats: {e}")


def video_capture_process(args, video_queue):
    logging.info(f"Starting video capture with type: {args.camera_type}")

    # Log supported formats before starting the capture
    if args.camera_type == 'rpi':
        _log_rpi_camera_modes()
    elif args.camera_type == 'usb':
        _log_usb_camera_formats(args.device_id)

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
        # Determine capture resolution, fallback to output resolution if not specified
        capture_width = args.capture_width if args.capture_width is not None else args.width
        capture_height = args.capture_height if args.capture_height is not None else args.height

        cap = cv2.VideoCapture(args.device_id, cv2.CAP_V4L2)
        if not cap.isOpened():
            return logging.error(f"Could not open camera device ID {args.device_id}.")

        # Set capture resolution and check if it was successful
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, capture_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, capture_height)
        cap.set(cv2.CAP_PROP_FPS, args.fps)

        actual_capture_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_capture_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if actual_capture_width != capture_width or actual_capture_height != capture_height:
            logging.warning(
                f"Failed to set capture resolution to {capture_width}x{capture_height}. "
                f"The camera may not support this resolution or it may have been adjusted."
            )
        logging.info(
            f"USB camera started with actual capture resolution: {actual_capture_width}x{actual_capture_height}")

        wait_time = 1.0 / args.fps
        while True:
            start_time = time.time()
            ret, frame = cap.read()
            timestamp = time.time()
            if not ret:
                continue

            # Resize frame if output size is different from capture size
            output_width = args.width
            output_height = args.height
            if frame.shape[1] != output_width or frame.shape[0] != output_height:
                frame = cv2.resize(
                    frame, (output_width, output_height), interpolation=cv2.INTER_AREA)

            ret, encoded_frame = cv2.imencode(
                '.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])

            if ret:
                if not video_queue.full():
                    # Send the final output dimensions
                    video_queue.put(
                        ('video', timestamp, output_width, output_height, encoded_frame.tobytes()))
                else:
                    logging.warning(
                        "Video queue full, dropping video frame.")
            elapsed = time.time() - start_time
            if wait_time > elapsed:
                time.sleep(wait_time - elapsed)
