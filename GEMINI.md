# GEMINI.md

## Project Overview

This project consists of a Python script designed to stream video and optionally audio from cameras connected to a Raspberry Pi over the network. The entire application is powered by the Flask web framework, providing a unified and extensible platform.

It supports both the official Raspberry Pi camera modules (via CSI) and standard USB webcams, with the camera type selectable via a command-line option.

*   **`main.py`**: This is the unified script for streaming. It uses a command-line argument (`--camera-type`) to switch between two modes:
    *   **`rpi` mode**: For the Raspberry Pi Camera Module. It uses the `picamera2` library to capture video.
    *   **`usb` mode**: For generic USB webcams. It uses `OpenCV` for video capture.
*   **Audio Streaming**: If a microphone is connected (e.g., a USB microphone or a HAT), audio can be streamed alongside the video in either mode by using the `--enable-audio` flag. This uses the `sounddevice` library.

In both modes, the script overlays the current timestamp onto the video frames. The web interface provides a video player and, if enabled, an audio player.

## Building and Running

### Dependencies

This project requires Python 3. You will need to install the necessary libraries.

**Core Dependencies:**

```bash
pip install Flask opencv-python numpy
```

**For `rpi` mode (Raspberry Pi Camera Module):**

You also need to install the `picamera2` library.

```bash
pip install picamera2
```

**For Optional Audio Streaming:**

To use the `--enable-audio` feature, you must install the `sounddevice` and `soundfile` libraries.

```bash
pip install sounddevice soundfile
```

### Running the Script

Use the `main.py` script with the `--camera-type` argument to specify your camera. The server will be accessible on all network interfaces by default.

**To stream from a Raspberry Pi Camera Module (Video Only):**

```bash
python3 main.py --camera-type rpi --port 8080
```

**To stream from a Raspberry Pi Camera Module (with Audio):**

1.  Connect a microphone to your Raspberry Pi.
2.  Run the script with the `--enable-audio` flag:
    ```bash
    python3 main.py --camera-type rpi --port 8080 --enable-audio
    ```

**To stream from a USB Webcam (with Audio):**

1.  Connect your USB camera and microphone.
2.  Run the script with the `--enable-audio` flag:
    ```bash
    python3 main.py --camera-type usb --port 8080 --enable-audio
    ```

After starting the script, open a web browser and navigate to `http://<your-pi-ip-address>:8080`. If audio is enabled, the page will include an audio player.

For all options, run `python3 main.py --help`.

## Development Conventions

*   The codebase is written in Python and uses the Flask framework.
*   Functionality is consolidated into the `main.py` script, with different capture methods handled in separate threads.
*   Camera and stream selection is handled via command-line arguments.
*   Video streams include a timestamp overlay for monitoring.
*   There are currently no automated tests or specific linting configurations evident in the project.