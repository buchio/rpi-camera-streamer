# GEMINI.md

## Project Overview

This project consists of a single shell script, `rpi-camera-streamer.sh`, designed to stream video from a Raspberry Pi to an RTMP server. The script supports two modes of operation based on the `VIDEO_DEVICE` environment variable.

1.  **Raspberry Pi Camera Module Mode**: If `VIDEO_DEVICE` is not set, the script uses `rpicam-vid` to capture video from the Raspberry Pi's native camera interface. In this mode, no audio is captured.
2.  **USB Camera/External Device Mode**: If `VIDEO_DEVICE` is set (e.g., to `/dev/video0`), the script uses `ffmpeg` to capture video directly from the specified V4L2 device and audio from an ALSA device specified by `AUDIO_DEVICE`.

The script pipes the captured video (and optionally audio) to `ffmpeg` for processing and streaming. It's configured to overlay a custom text message and a real-time timestamp onto the video feed before sending it to the specified RTMP endpoint.

Configuration settings (like resolution, framerate, device names) are sourced from a host-specific settings file: `settings/$(hostname).sh`.

## Dependencies

-   **`libcamera-apps`**: Provides the `rpicam-vid` command for camera capture (for Raspberry Pi Camera Module mode).
-   **`ffmpeg`**: Required for video/audio encoding, overlaying filters, and RTMP streaming.
-   **`alsa-utils`**: Provides tools for ALSA audio capture (for USB Camera mode).

## Running the Script

1.  **Configuration**:
    *   Create a host-specific configuration file under `settings/`, e.g., `settings/my-pi.sh`.
    *   Inside this file, define variables like `WIDTH`, `HEIGHT`, `FRAMERATE`, and optionally `VIDEO_DEVICE` and `AUDIO_DEVICE`.
    *   Edit the main `rpi-camera-streamer.sh` to set the `RTMP_URL`.
    *   Prepare a text file for the overlay message in `titles/`.
2.  **Execution**: Make the script executable and run it.
    ```bash
    chmod +x rpi-camera-streamer.sh
    ./rpi-camera-streamer.sh
    ```

The script is designed to run continuously until manually stopped.

## Development Conventions

-   The core logic is contained within the `rpi-camera-streamer.sh` bash script.
-   The script uses an `if/else` block to switch between capture methods.
-   Host-specific configuration is externalized to files in the `settings/` directory.
-   The script leverages standard Linux utilities and pipelines.