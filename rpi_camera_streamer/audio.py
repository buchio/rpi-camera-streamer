
import time
import logging
import base64
import os

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    SOUNDDEVICE_AVAILABLE = False


def add_audio_args(parser):
    parser.add_argument('--enable-audio', action='store_true')
    parser.add_argument('--audio-device', type=int, default=None)
    parser.add_argument('--audio-channels', type=int, default=1,
                        help="Number of audio channels (1=mono).")
    parser.add_argument('--audio-samplerate', type=int, default=None,
                        help="Audio sample rate in Hz. Defaults to device default.")


def audio_capture_process(args, audio_queue):
    try:
        # Increase priority of the audio process
        os.nice(-10)
        logging.info(f"Audio process priority set to: {os.nice(0)}")
    except OSError as e:
        logging.warning(f"Failed to set audio process priority: {e}")

    try:
        device_id = args.audio_device
        if device_id is None:
            # If no device is specified, use the default input device
            device_id = sd.default.device[0]
            logging.info(
                f"No audio device specified, using default input device index: {device_id}")

        device_info = sd.query_devices(device_id, 'input')
        if args.audio_samplerate is None:
            samplerate = int(device_info['default_samplerate'])
            logging.info(f"Using default sample rate: {samplerate} Hz")
        else:
            samplerate = args.audio_samplerate
            logging.info(f"Using specified sample rate: {samplerate} Hz")
        channels = args.audio_channels
        blocksize = 2048  # Use a moderate, fixed block size
        logging.info(
            f"Using audio device: {device_info['name']} with blocksize {blocksize}")
    except Exception as e:
        return logging.error(f"Error querying audio devices: {e}")

    def callback(indata, frames, time_info, status):
        if status:
            logging.warning(status)
        timestamp = time.time()
        raw_data = indata.tobytes()
        if not audio_queue.full():
            audio_queue.put(('audio', timestamp, raw_data))
        else:
            logging.warning("Audio queue full, dropping audio frame.")

    with sd.InputStream(device=device_id, samplerate=samplerate, channels=channels, dtype='int16', blocksize=blocksize, callback=callback):
        while True:
            time.sleep(10)
