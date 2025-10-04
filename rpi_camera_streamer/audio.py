
import time
import logging

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    SOUNDDEVICE_AVAILABLE = False


def audio_capture_thread(args, combined_queue):
    if not SOUNDDEVICE_AVAILABLE:
        logging.error(
            "sounddevice library not found. Audio stream will not start.")
        return

    try:
        device_info = sd.query_devices(args.audio_device, 'input')
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
        if not combined_queue.full():
            combined_queue.put(('audio', timestamp, indata.tobytes()))
        else:
            logging.warning("Combined queue full, dropping audio frame.")

    with sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=blocksize, callback=callback):
        while True:
            time.sleep(10)
