# GEMINI.md

## Project Overview

This project consists of a single shell script, `rpi-camera-streamer.sh`, designed to stream video from a Raspberry Pi camera to an RTMP server.

The script utilizes `rpicam-vid` to capture high-resolution video and pipes it to `ffmpeg` for processing and streaming. It's configured to overlay a custom text message and a real-time timestamp onto the video feed before sending it to the specified RTMP endpoint.

## Dependencies

-   **`libcamera-apps`**: Provides the `rpicam-vid` command for camera capture. This is standard on recent Raspberry Pi OS distributions.
-   **`ffmpeg`**: Required for video encoding, overlaying filters, and RTMP streaming.

## Running the Script

1.  **Configuration**: Before running, you may need to edit `rpi-camera-streamer.sh` to set variables like `RTMP_URL`, `WIDTH`, `HEIGHT`, and `MESSAGE` to match your environment and preferences.
2.  **Execution**: Make the script executable and run it.
    ```bash
    chmod +x rpi-camera-streamer.sh
    ./rpi-camera-streamer.sh
    ```

The script is designed to run continuously until manually stopped.

## Development Conventions

-   The core logic is contained within the `rpi-camera-streamer.sh` bash script.
-   Configuration is managed via variables at the top of the script for easy access.
-   The script is designed for clarity and directness, leveraging standard Linux utilities and pipelines.
