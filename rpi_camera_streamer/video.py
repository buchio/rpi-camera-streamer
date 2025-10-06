import io
import time
import logging
import subprocess
import re
import os
import base64

# --- Conditional Imports ---
try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False

try:
    import v4l2
    import fcntl
    import mmap
    import ctypes
    from select import select
    PYV4L2_AVAILABLE = True
except ImportError:
    PYV4L2_AVAILABLE = False

# --- Argument Parsing ---


def add_video_args(parser):
    parser.add_argument('--camera-type', type=str, required=True,
                        choices=['rpi', 'usb'], help="Type of camera to use.")
    parser.add_argument('--width', type=int, default=640,
                        help="Width for video capture.")
    parser.add_argument('--height', type=int, default=480,
                        help="Height for video capture.")
    parser.add_argument('--fps', type=int, default=15,
                        help="Frames per second.")
    parser.add_argument('--quality', type=int, default=70,
                        help="JPEG encoding quality (for RPi camera).")
    parser.add_argument('--device-id', type=int, default=0,
                        help="USB camera device ID (e.g., 0 for /dev/video0).")

# --- Logging Helpers ---


def _log_rpi_camera_modes():
    """Logs the sensor modes available for a picamera2 device."""
    if not PICAMERA2_AVAILABLE:
        return
    try:
        picam2 = Picamera2()
        logging.info("--- RPi Camera Supported Modes ---")
        for mode in picam2.sensor_modes:
            logging.info(mode)
        logging.info("--------------------------------")
        picam2.close()
    except Exception as e:
        logging.warning(f"Could not enumerate RPi camera modes: {e}")


def _log_usb_camera_formats(device_id):
    """Logs supported formats and resolutions for a USB camera using v4l2-ctl."""
    device_path = f"/dev/video{device_id}"
    logging.info(
        f"--- USB Camera Supported Formats for {device_path} (via v4l2-ctl) ---")
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--device', device_path, '--list-formats-ext'],
            capture_output=True, text=True, check=True
        )
        output = result.stdout
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

# --- V4L2 Capture Process (for USB) ---


def _v4l2_capture(args, video_queue):
    if not PYV4L2_AVAILABLE:
        logging.error(
            "pyv4l2 library is not installed. USB camera stream will not start.")
        return

    device_path = f"/dev/video{args.device_id}"
    buffers = []
    device = None
    try:
        device = open(device_path, 'rb+', buffering=0)

        caps = v4l2.v4l2_capability()
        fcntl.ioctl(device, v4l2.VIDIOC_QUERYCAP, caps)
        if not (caps.capabilities & v4l2.V4L2_CAP_VIDEO_CAPTURE):
            logging.error(f"{device_path} does not support video capture.")
            return
        if not (caps.capabilities & v4l2.V4L2_CAP_STREAMING):
            logging.error(f"{device_path} does not support streaming.")
            return

        fmt = v4l2.v4l2_format()
        fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        fmt.fmt.pix.width = args.width
        fmt.fmt.pix.height = args.height
        fmt.fmt.pix.pixelformat = v4l2.V4L2_PIX_FMT_MJPEG
        fmt.fmt.pix.field = v4l2.V4L2_FIELD_ANY
        try:
            fcntl.ioctl(device, v4l2.VIDIOC_S_FMT, fmt)
        except OSError as e:
            if e.errno == 22:  # Invalid argument
                logging.error(
                    f"Failed to set format to MJPEG {args.width}x{args.height}.")
                logging.error(
                    "The camera may not support this format or resolution.")
                logging.error(
                    "Please check the output of 'v4l2-ctl --list-formats-ext' for supported modes.")
                return
            else:
                raise

        actual_width = fmt.fmt.pix.width
        actual_height = fmt.fmt.pix.height
        if actual_width != args.width or actual_height != args.height:
            logging.warning(
                f"Resolution was adjusted by driver to {actual_width}x{actual_height}")

        req = v4l2.v4l2_requestbuffers()
        req.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        req.count = 4
        req.memory = v4l2.V4L2_MEMORY_MMAP
        fcntl.ioctl(device, v4l2.VIDIOC_REQBUFS, req)

        for i in range(req.count):
            buf = v4l2.v4l2_buffer()
            buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
            buf.memory = v4l2.V4L2_MEMORY_MMAP
            buf.index = i
            fcntl.ioctl(device, v4l2.VIDIOC_QUERYBUF, buf)
            mm = mmap.mmap(device.fileno(), buf.length, mmap.MAP_SHARED,
                           mmap.PROT_READ | mmap.PROT_WRITE, offset=buf.m.offset)
            buffers.append(mm)
            fcntl.ioctl(device, v4l2.VIDIOC_QBUF, buf)

        buf_type = ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
        fcntl.ioctl(device, v4l2.VIDIOC_STREAMON, buf_type)
        logging.info(
            f"V4L2 capture started on {device_path} at {actual_width}x{actual_height}")

        while True:
            r, _, _ = select([device], [], [])
            if device in r:
                buf = v4l2.v4l2_buffer()
                buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
                buf.memory = v4l2.V4L2_MEMORY_MMAP
                fcntl.ioctl(device, v4l2.VIDIOC_DQBUF, buf)
                jpeg_data = buffers[buf.index].read(buf.bytesused)
                buffers[buf.index].seek(0)
                raw_size = len(jpeg_data)
                encoded_data = base64.b64encode(jpeg_data)
                if not video_queue.full():
                    video_queue.put(
                        ('video', time.time(), actual_width, actual_height, raw_size, encoded_data))
                fcntl.ioctl(device, v4l2.VIDIOC_QBUF, buf)

    except (IOError, OSError) as e:
        logging.error(f"V4L2 Error: {e}")
    finally:
        if device:
            try:
                buf_type = ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
                fcntl.ioctl(device, v4l2.VIDIOC_STREAMOFF, buf_type)
            except (IOError, OSError):
                pass
            for mm in buffers:
                mm.close()
            device.close()
        logging.info("V4L2 capture stopped.")

# --- RPi Camera Capture Process ---


def _rpi_capture(args, video_queue):
    if not PICAMERA2_AVAILABLE:
        logging.error(
            "picamera2 library not found. Raspberry Pi camera stream will not start.")
        return
    picam2 = Picamera2()
    try:
        video_config = picam2.create_video_configuration(main={"format": "XBGR8888", "size": (
            args.width, args.height)}, controls={"FrameRate": args.fps})
        picam2.configure(video_config)
        actual_config = picam2.camera_configuration()
        actual_width = actual_config['main']['size'][0]
        actual_height = actual_config['main']['size'][1]
        logging.info(
            f"RPi camera configured to: {actual_width}x{actual_height}")

        encoder = JpegEncoder(q=args.quality)
        output = io.BytesIO()
        picam2.start_recording(encoder, FileOutput(output))

        # In this mode, we simply sleep and grab the latest frame from the buffer.
        frame_duration = 1.0 / args.fps
        while True:
            time.sleep(frame_duration)
            timestamp = time.time()
            frame_data = output.getvalue()
            output.seek(0)
            output.truncate()
            if not video_queue.full():
                video_queue.put(
                    ('video', timestamp, actual_width, actual_height, frame_data))
            else:
                logging.warning("Video queue full, dropping video frame.")
    finally:
        if picam2.is_open:
            picam2.stop_recording()
        picam2.close()
        logging.info("RPi camera capture stopped.")

# --- Main Process Function ---


def video_capture_process(args, video_queue):
    try:
        # Decrease priority of the video process
        os.nice(10)
        logging.info(f"Video process priority set to: {os.nice(0)}")
    except OSError as e:
        logging.warning(f"Failed to set video process priority: {e}")

    logging.info(f"Starting video capture with type: {args.camera_type}")

    if args.camera_type == 'rpi':
        _log_rpi_camera_modes()
        _rpi_capture(args, video_queue)
    elif args.camera_type == 'usb':
        _log_usb_camera_formats(args.device_id)
        _v4l2_capture(args, video_queue)
