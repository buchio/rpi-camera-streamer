#!/usr/bin/python3
import io
import logging
import socket
import socketserver
import sys
from http import server
from threading import Condition, Thread
from datetime import datetime

import cv2

# --- 設定 ---
PORT = 8000
CAMERA_DEVICE_ID = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
TARGET_FPS = 15
JPEG_QUALITY = 70
# ------------

# IPアドレスの取得
try:
    connect_interface = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    connect_interface.connect(("8.8.8.8", 80))
    myip = connect_interface.getsockname()[0]
    connect_interface.close()
except OSError:
    myip = '127.0.0.1'

# HTMLページの内容
PAGE = f'''
<html>
<head>
<title>USB Camera Stream</title>
</head>
<body>
<img src="stream.mjpg" width="{FRAME_WIDTH}" height="{FRAME_HEIGHT}" />
</body>
</html>
'''

class StreamingOutput(io.BufferedIOBase):
    '''
    カメラからのフレームを保持し、スレッド間で安全に受け渡すためのクラス
    '''
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

class StreamingHandler(server.BaseHTTPRequestHandler):
    '''
    HTTPリクエストを処理するハンドラクラス
    '''
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    '''
    マルチスレッドでリクエストを処理するHTTPサーバー
    '''
    allow_reuse_address = True
    daemon_threads = True

def capture_loop(output):
    '''
    OpenCVを使ってカメラからフレームをキャプチャし、StreamingOutputに書き込む
    '''
    cap = cv2.VideoCapture(CAMERA_DEVICE_ID, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"エラー: カメラデバイスID {CAMERA_DEVICE_ID} を開けませんでした。")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
    print("カメラを正常にオープンしました。ストリーミングを開始します。")

    wait_time = 1.0 / TARGET_FPS

    while True:
        start_time = datetime.now()
        ret, frame = cap.read()
        if not ret:
            print("エラー: フレームを読み込めませんでした。")
            continue

        # タイムスタンプを描画
        timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        cv2.putText(img=frame, text=timestamp, org=(10, 20),
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=0.5,
                    color=(255, 255, 255), thickness=1)

        # フレームをJPEGにエンコード
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if ret:
            output.write(buffer.tobytes())

        # フレームレートを維持するための待機
        elapsed = (datetime.now() - start_time).total_seconds()
        sleep_time = wait_time - elapsed
        if sleep_time > 0:
            cv2.waitKey(int(sleep_time * 1000))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    output = StreamingOutput()
    
    # カメラキャプチャをバックグラウンドスレッドで開始
    capture_thread = Thread(target=capture_loop, args=(output,), daemon=True)
    capture_thread.start()

    try:
        address = ('', PORT)
        server = StreamingServer(address, StreamingHandler)
        print(f"サーバーを開始しました。 http://{myip}:{PORT}/index.html でアクセスしてください。")
        server.serve_forever()
    except KeyboardInterrupt:
        print("サーバーを停止します。")
    finally:
        # このスクリプトでは明示的なリソース解放処理は不要
        pass
