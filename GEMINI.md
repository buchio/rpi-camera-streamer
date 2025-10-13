# GEMINI.md

## Project Overview

This project, located in the `ffmpeg/` directory, consists of a shell script `rpi-camera-streamer.sh` for streaming from a Raspberry Pi. It's highly flexible, supporting various combinations of video and audio sources based on environment variables defined in host-specific setting files.

## Core Logic

The script's behavior is determined by the presence of `VIDEO_DEVICE` and `AUDIO_DEVICE` variables in a `settings/$(hostname).sh` file:

1.  **Video & Audio:** If both `VIDEO_DEVICE` and `AUDIO_DEVICE` are set, it streams from a V4L2 device (e.g., USB webcam) and an ALSA audio device.
2.  **Audio Only:** If `AUDIO_DEVICE` is set but `VIDEO_DEVICE` is empty, it streams audio only from the specified ALSA device.
3.  **Video Only (USB Cam):** If `VIDEO_DEVICE` is set but `AUDIO_DEVICE` is empty, it streams video only from the V4L2 device.
4.  **Video Only (Pi Cam):** If both `VIDEO_DEVICE` and `AUDIO_DEVICE` are empty, it falls back to using `rpicam-vid` for the native Raspberry Pi camera module.

## Key Files

-   `ffmpeg/rpi-camera-streamer.sh`: The main executable script containing the core streaming logic.
-   `ffmpeg/settings/`: Directory containing host-specific configuration files. The script sources `settings/$(hostname).sh` on startup.
-   `ffmpeg/titles/`: Contains text files used for video overlays.
-   `ffmpeg/systemd/`: Contains a `systemd` service unit template for running the script as a background service.
-   `README.md`: The user-facing documentation.
-   `GEMINI.md`: This internal development context file.

## Development Conventions

-   Logic is controlled by environment variables sourced from external settings files.
-   The script uses nested `if/then/else` blocks to handle the four different operating modes.
-   It leverages standard Linux utilities like `ffmpeg`, `rpicam-vid`, and `alsa`.
