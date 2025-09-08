import socket
import sys
from datetime import datetime

import cv2
from picamera2 import Picamera2, MappedArray
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

from stream import StreamingServer, StreamingHandler, StreamingOutput

PORT = 8080
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Get current IP address
try:
    connect_interface = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    connect_interface.connect(("8.8.8.8", 80))
    myip = connect_interface.getsockname()[0]
    connect_interface.close()
except OSError:
    myip = '127.0.0.1'

message = 'RPi Camera'
if len(sys.argv) > 1:
    message = sys.argv[1]

# HTML page content
PAGE = f"""
<html>
<head>
<title>{message}</title>
</head>
<body>
<img src="stream.mjpg" width="{FRAME_WIDTH}" height="{FRAME_HEIGHT}" />
</body>
</html>
"""

def draw_timestamp(request):
    """Draws a timestamp on the frame before encoding."""
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

if __name__ == '__main__':
    picam2 = Picamera2()
    video_config = picam2.create_video_configuration(
        main={"format": "XBGR8888", "size": (FRAME_WIDTH, FRAME_HEIGHT)},
        controls={"FrameRate": 15}
    )
    picam2.configure(video_config)
    picam2.pre_callback = draw_timestamp
    
    output = StreamingOutput()
    encoder = JpegEncoder(q=70)
    picam2.start_recording(encoder, FileOutput(output))

    try:
        address = ('', PORT)
        
        # Set the output and page for the handler
        StreamingHandler.output = output
        StreamingHandler.page = PAGE
        
        server = StreamingServer(address, StreamingHandler)
        print(f"Server started. Access at http://{myip}:{PORT}/index.html")
        server.serve_forever()
    finally:
        picam2.stop_recording()