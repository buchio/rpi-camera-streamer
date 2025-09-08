#!/usr/bin/python3
from flask import Flask, Response
import cv2
from datetime import datetime
import time
import sys

# --- 最適化のための設定 ---
# カメラデバイスのID
CAMERA_DEVICE_ID = 0

# 解像度を低めに設定 (640x480 -> 320x240)
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# 目標フレームレート (1秒あたりのコマ数)
TARGET_FPS = 5

# JPEGエンコードの品質 (1-100, 低いほど圧縮率が高い)
JPEG_QUALITY = 30
# -----------------------------

app = Flask(__name__)

def generate_frames():
    """カメラからフレームを読み込み、MJPEG形式で出力するジェネレータ関数"""
    cap = cv2.VideoCapture(CAMERA_DEVICE_ID, cv2.CAP_V4L2)

    if not cap.isOpened():
        print(f"エラー: カメラデバイスID {CAMERA_DEVICE_ID} を開けませんでした。")
        sys.exit()
    
    # カメラに解像度とフレームレートを設定
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)

    print("カメラを正常にオープンしました。ストリーミングを開始します。")

    # フレーム間の待機時間を計算
    wait_time = 1.0 / TARGET_FPS

    while True:
        # 前回の処理開始時間を記録
        start_time = time.time()
        
        ret, frame = cap.read()
        if not ret:
            print("エラー: フレームを読み込めませんでした。5秒後に再試行します。")
            time.sleep(5)
            continue

        timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        cv2.putText(img=frame,
                    text=timestamp,
                    org=(10, 20), # 解像度が低いのでY座標を調整
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                    fontScale=0.5, # 解像度が低いのでフォントサイズを調整
                    color=(255, 255, 255),
                    thickness=1)
        
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ret:
            continue
        
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # 処理にかかった時間を計算
        elapsed_time = time.time() - start_time
        # 待機すべき残り時間があれば待機
        sleep_time = wait_time - elapsed_time
        if sleep_time > 0:
            time.sleep(sleep_time)

@app.route('/video_feed')
def video_feed():
    """ビデオストリームを配信するルート"""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    """トップページ。ビデオストリームを表示するHTMLを返す"""
    return f"""
    <html>
        <head>
            <title>USB Camera Stream</title>
        </head>
        <body>
            <h1>USB Camera Stream</h1>
            <img src="/video_feed" width="{FRAME_WIDTH}" height="{FRAME_HEIGHT}">
        </body>
    </html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, threaded=True)
