import io
import logging
import socketserver
from http import server
from threading import Condition
import cv2
from datetime import datetime


def draw_overlay(frame, message=None):
    """フレームにタイムスタンプとオプションのメッセージを描画する"""
    c1 = (0, 0, 0)      # 影用の黒
    c2 = (255, 255, 255) # テキスト用の白
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1
    t1 = 5 # 影の太さ
    t2 = 2 # テキストの太さ

    # タイムスタンプ (640x480解像度用の座標)
    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    ts_pos = (260, 470)
    cv2.putText(frame, timestamp, ts_pos, font, scale, c1, t1)
    cv2.putText(frame, timestamp, ts_pos, font, scale, c2, t2)

    # オプションのメッセージ
    if message:
        msg_pos = (10, 30)
        cv2.putText(frame, message, msg_pos, font, scale, c1, t1)
        cv2.putText(frame, message, msg_pos, font, scale, c2, t2)

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

class StreamingHandler(server.BaseHTTPRequestHandler):
    # These will be set by the main script
    output = None
    page = ""

    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = self.page.encode('utf-8')
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
                    with self.output.condition:
                        self.output.condition.wait()
                        frame = self.output.frame
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
    allow_reuse_address = True
    daemon_threads = True
