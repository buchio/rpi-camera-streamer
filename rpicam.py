import io
import logging
import socket
import socketserver
import sys

from http import server
from threading import Condition
from datetime import datetime

# OpenCVライブラリをインポート
import cv2
import numpy as np

from picamera2 import Picamera2, MappedArray
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput


port = 8080

# Get current IP address
connect_interface = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
connect_interface.connect(("8.8.8.8", 80))
myip = connect_interface.getsockname()[0]
connect_interface.close()

message = 'TEST'
if len(sys.argv) > 1:
    message = sys.argv[1]

# HTMLページの内容
PAGE = f"""
<html>
<head>
<title>{message}</title>
</head>
<body>
<img src="stream.mjpg" width="640" height="480" />
</body>
</html>
"""

# ストリーミング用の出力クラス
class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

# HTTPリクエストを処理するハンドラクラス
class StreamingHandler(server.BaseHTTPRequestHandler):
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

# ストリーミングサーバーのクラス
class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

# --- OpenCVを使ったコールバック関数 ---
def draw_timestamp(request):
    """OpenCVを使い、エンコード直前のフレームに時刻を描画する"""
    c1 = (0, 0, 0)
    c2 = (255, 255, 255)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1
    t1 = 5
    t2 = 2
    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    with MappedArray(request, 'main') as m:
        cv2.putText(m.array, timestamp, (260, 470), font, scale, c1, t1)
        cv2.putText(m.array, timestamp, (260, 470), font, scale, c2, t2)
        cv2.putText(m.array, message, (10, 30), font, scale, c1, t1)
        cv2.putText(m.array, message, (10, 30), font, scale, c2, t2)

# メイン処理
picam2 = Picamera2()
# ストリーミングに適した解像度に設定
video_config = picam2.create_video_configuration(
    main={"format": "XBGR8888", "size": (640, 480)},
    controls={"FrameRate": 15}
)
picam2.configure(video_config)
picam2.pre_callback = draw_timestamp
encoder = JpegEncoder(q=70)
output = StreamingOutput()
# JpegEncoderを使い、FileOutputとしてoutputオブジェクトを指定
picam2.start_recording(encoder, FileOutput(output))

try:
    address = ('', port)
    server = StreamingServer(address, StreamingHandler)
    print(f"サーバーを開始しました。 http://{myip}:{port}/index.html でアクセスしてください。")
    server.serve_forever()
finally:
    picam2.stop_recording()
