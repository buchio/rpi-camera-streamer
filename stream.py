import io
import logging
import socketserver
from http import server
from threading import Condition
from datetime import datetime

# OpenCVライブラリをインポート
import cv2
import numpy as np

from picamera2 import Picamera2, MappedArray
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

# HTMLページの内容
PAGE = """
<html>
<head>
<title>rasp1-ubuntu-1</title>
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
    colour = (0, 255, 0)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1
    thickness = 2
    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    with MappedArray(request, 'main') as m:
        cv2.putText(m.array, timestamp, (260, 470), font, scale, colour, thickness)
        cv2.putText(m.array, 'rasp1-ubuntu-1', (10, 30), font, scale, colour, thickness)

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
    address = ('', 8080)
    server = StreamingServer(address, StreamingHandler)
    print("サーバーを開始しました。 http://<Raspberry PiのIPアドレス>:8080/index.html でアクセスしてください。")
    server.serve_forever()
finally:
    picam2.stop_recording()
