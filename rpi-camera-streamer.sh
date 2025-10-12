#!/bin/bash

set -x

BASEDIR=$(dirname $(readlink -f $0))

source ${BASEDIR}/settings/$(hostname).sh

RTMP_URL="rtmp://rasp4-ubuntu-1.local/live/$(hostname)"
FONT_PATH="/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"
MESSAGE_FILE="${BASEDIR}/titles/$(hostname).txt"
LOCALTIME_FILE="${BASEDIR}/localtime.txt"
FILTER_SCALE="scale=${OUTPUT_WIDTH}:${OUTPUT_HEIGHT}"
FILTER1="drawtext=fontfile=${FONT_PATH}:textfile=${MESSAGE_FILE}:fontcolor=white:fontsize=48:box=1:boxcolor=black@0.5:x=30:y=30"
FILTER2="drawtext=fontfile=${FONT_PATH}:textfile=${LOCALTIME_FILE}:fontcolor=white:fontsize=48:box=1:boxcolor=black@0.5:x=w-text_w-30:y=h-text_h-30"
FILTER_CHAIN="${FILTER_SCALE},${FILTER1},${FILTER2}"

if [ "${VIDEO_DEVICE}" = "" ]
then
    # --- rpicam-vid と ffmpeg を実行 ---
    rpicam-vid -t 0 --width ${WIDTH} --height ${HEIGHT} --framerate ${FRAMERATE} --codec yuv420 --nopreview -o - | \
    ffmpeg \
        -probesize 4M \
        -f rawvideo -pix_fmt yuv420p -s ${WIDTH}x${HEIGHT} -r ${FRAMERATE} -i - \
        -vf "${FILTER_CHAIN}" \
        -c:v h264_v4l2m2m -b:v 2M -f flv "${RTMP_URL}"
else
    # --- FFmpegコマンドの実行 ---
    ffmpeg \
        -thread_queue_size 1024 \
        -f v4l2 -s ${WIDTH}x${HEIGHT} -r ${FRAMERATE} -i "${VIDEO_DEVICE}" \
        -thread_queue_size 1024 \
        -f alsa -i "${AUDIO_DEVICE}" \
        -vf "${FILTER_CHAIN}" \
        -c:v h264_v4l2m2m -b:v 2000k -pix_fmt yuv420p  \
        -c:a aac -b:a 128k -ar 22050  \
        -f flv "${RTMP_URL}"
fi
