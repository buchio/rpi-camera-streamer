# GEMINI.md

## Project Overview

This project consists of a Python script designed to stream video from cameras connected to a Raspberry Pi over the network. It supports both the official Raspberry Pi camera modules (via CSI) and standard USB webcams, with the camera type selectable via a command-line option.

*   **`main.py`**: This is the unified script for video streaming. It uses a command-line argument (`--camera-type`) to switch between two modes:
    *   **`rpi` mode**: For the Raspberry Pi Camera Module. It uses the `picamera2` library to capture video and the standard Python `http.server` to stream it as an MJPEG feed.
    *   **`usb` mode**: For generic USB webcams. It uses `OpenCV` to capture the video feed and `Flask` to create a web server that streams the video as an MJPEG feed.

In both modes, the script overlays the current timestamp onto the video frames.

## Building and Running

### Dependencies

This project requires Python 3. You will need to install the necessary libraries depending on the camera you intend to use. While there is no `requirements.txt` file, you can install the dependencies based on the `import` statements in `main.py`.

**For both camera types (core dependencies):**

```bash
pip install opencv-python
```

**For `rpi` mode (Raspberry Pi Camera Module):**

```bash
pip install picamera2
```

**For `usb` mode (USB Webcam):**

```bash
pip install Flask
```

### Running the Script

Use the `main.py` script with the `--camera-type` argument to specify your camera.

**To stream from a Raspberry Pi Camera Module:**

1.  Connect your camera module to the Raspberry Pi's CSI port.
2.  Run the script:
    ```bash
    python3 main.py --camera-type rpi --port 8080
    ```
3.  Open a web browser and navigate to `http://<your-pi-ip-address>:8080`.

**To stream from a USB Webcam:**

1.  Connect your USB camera to one of the Raspberry Pi's USB ports.
2.  Run the script:
    ```bash
    python3 main.py --camera-type usb --port 8080
    ```
3.  Open a web browser and navigate to `http://<your-pi-ip-address>:8080`.

## Development Conventions

*   The codebase is written in Python.
*   Functionality is consolidated into the `main.py` script.
*   Camera selection is handled via command-line arguments for clarity and flexibility.
*   Video streams include a timestamp overlay for monitoring.
*   There are currently no automated tests or specific linting configurations evident in the project.