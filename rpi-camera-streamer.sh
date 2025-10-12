#!/bin/bash

set -x

BASEDIR=$(dirname $(readlink -f $0))

# --- 設定項目 ---
RTMP_URL="rtmp://rasp4-ubuntu-1.local/live/machineroom2"
WIDTH=1920
HEIGHT=1080
FRAMERATE=0.5
FONT_PATH="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

FILTER_SCALE="scale=1280:720"
FONT_PATH="/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"

MESSAGE_FILE="${BASEDIR}/title_rasp3-ubuntu-1.txt"

FILTER1="drawtext=fontfile=${FONT_PATH}:textfile=${MESSAGE_FILE}:fontcolor=white:fontsize=36:box=1:boxcolor=black@0.5:x=10:y=10"
FILTER2="drawtext=fontfile=${FONT_PATH}:text='%{localtime\\:%Y-%m-%d %H\\\\\\:%M\\\\\\:%S}':fontcolor=white:fontsize=24:box=1:boxcolor=black@0.5:x=w-text_w-10:y=h-text_h-10"
FILTER_CHAIN="${FILTER_SCALE},${FILTER1},${FILTER2}"

# --- rpicam-vid と ffmpeg を実行 ---
rpicam-vid -t 0 --width ${WIDTH} --height ${HEIGHT} --framerate ${FRAMERATE} --codec yuv420 --nopreview -o - | \
ffmpeg \
    -f rawvideo -pix_fmt yuv420p -s ${WIDTH}x${HEIGHT} -r ${FRAMERATE} -i - \
    -vf "${FILTER_CHAIN}" \
    -c:v h264_v4l2m2m -b:v 2M -f flv "${RTMP_URL}"
