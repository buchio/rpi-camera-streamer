# GEMINI.md

## Project Overview

This project consists of a Python script designed to stream video and audio from cameras connected to a Raspberry Pi over the network. The entire application is powered by the Flask web framework, providing a unified and extensible platform.

It supports both the official Raspberry Pi camera modules (via CSI) and standard USB webcams, with the camera type selectable via a command-line option.

*   **`main.py`**: This is the unified script for video and audio streaming. It uses a command-line argument (`--camera-type`) to switch between two modes:
    *   **`rpi` mode**: For the Raspberry Pi Camera Module. It uses the `picamera2` library to capture video.
    *   **`usb` mode**: For generic USB webcams. It uses `OpenCV` for video capture and `sounddevice` for audio capture.

In both modes, the script overlays the current timestamp onto the video frames. The web interface provides a video player and, for `usb` mode, an audio player.

## Building and Running

### Dependencies

This project requires Python 3. You will need to install the necessary libraries. You can install all core dependencies with the following command:

```bash
pip install Flask opencv-python numpy
```

**For `rpi` mode (Raspberry Pi Camera Module):**

You also need to install the `picamera2` library.

```bash
pip install picamera2
```

**For `usb` mode (USB Webcam with Audio):**

You also need to install the `sounddevice` and `soundfile` libraries for audio streaming.

```bash
pip install sounddevice soundfile
```

### Running the Script

Use the `main.py` script with the `--camera-type` argument to specify your camera. The server will be accessible on all network interfaces by default.

**To stream from a Raspberry Pi Camera Module:**

1.  Connect your camera module to the Raspberry Pi's CSI port.
2.  Run the script:
    ```bash
    python3 main.py --camera-type rpi --port 8080
    ```
3.  Open a web browser and navigate to `http://<your-pi-ip-address>:8080`.

**To stream from a USB Webcam (with Audio):**

1.  Connect your USB camera and microphone to the Raspberry Pi's USB ports.
2.  Run the script:
    ```bash
    python3 main.py --camera-type usb --port 8080
    ```
3.  Open a web browser and navigate to `http://<your-pi-ip-address>:8080`. The page will include an audio player.
4.  You can adjust audio settings with arguments like `--audio-samplerate`. For all options, run `python3 main.py --help`.

## Development Conventions

*   The codebase is written in Python and uses the Flask framework.
*   Functionality is consolidated into the `main.py` script, with different capture methods handled in separate threads.
*   Camera and stream selection is handled via command-line arguments.
*   Video streams include a timestamp overlay for monitoring.
*   There are currently no automated tests or specific linting configurations evident in the project.
