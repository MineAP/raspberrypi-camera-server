import io
import time
import picamera

from flask import Flask, Response, render_template
from flask_restful import Api, Resource

app = Flask(__name__)
api = Api(app)

# Create an in-memory stream
my_stream = io.BytesIO()
with picamera.PiCamera() as camera:
    camera.start_preview()
    # Camera warm-up time
    time.sleep(2)
    camera.capture(my_stream, 'jpeg')

    data:bytes = my_stream.getvalue()

    # 画像を保存
    with open('./tmp.jpg', 'wb') as out:
        out.write(data)
