import base64
import datetime
import json
import os
import subprocess
import threading
import traceback
from io import BytesIO
from queue import Queue
from time import sleep
from typing import Optional

from flask import Flask, Response, render_template
from flask_restful import Api, Resource
from PIL import Image
from pytz import utc

import adafruit_dht
import board
from picamera2 import Picamera2
from libcamera import Transform

'''
Flaskを使ったRaspberryPi Camera画像配信サーバー
'''

app: Flask = Flask(__name__)
api: Api = Api(app)
vs = None

# read DHT22 data using GPIO 4
dht_device = adafruit_dht.DHT22(board.D4)
dht_lock = threading.Lock()


class DHTReading:
    def __init__(self, temperature, humidity):
        self.temperature = temperature
        self.humidity = humidity

    def is_valid(self):
        return self.temperature is not None and self.humidity is not None


class PiVideoStream:
    '''
    バックグラウンドで動く画像収集ストリーム
    https://research.itplants.com/?p=1562
    '''

    def __init__(self, resolution=(320, 240), framerate=32):
        print(f'PiVideoStream.__init__()')
        # initialize the camera
        self.camera = Picamera2()
        self.config = self.camera.create_video_configuration(
            main={"size": resolution, "format": "BGR888"},
            transform=Transform(hflip=True, vflip=True),
            controls={"FrameRate": framerate}
        )
        self.camera.configure(self.config)

        # initialize the frame and the variable used to indicate
        # if the thread should be stopped
        self.frame = None
        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
        print(f'PiVideoStream.start()')
        # start the thread to read frames from the video stream
        self.camera.start()
        threading.Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        # keep looping infinitely until the thread is stopped
        while not self.stopped:
            frame = self.camera.capture_array("main")
            with self.lock:
                self.frame = frame

        self.camera.stop()
        self.camera.close()

    def read(self):
        # return the frame most recently read
        with self.lock:
            return self.frame

    def stop(self):
        print(f'PiVideoStream.stop()')
        # indicate that the thread should be stopped
        self.stopped = True

    def seek(self):
        pass


def capture():
    global vs
    if vs is None:
        return None

    return vs.read()


def capture_image() -> Optional[bytes]:
    '''
    convert narray to jpeg binary
    '''

    frame = capture()
    if frame is None:
        return None

    pil_img: Image = Image.fromarray(frame)
    buffer = BytesIO()
    pil_img.save(buffer, format='jpeg')

    # save image file for debug
    filepath = './tmp.jpg'
    if os.path.exists(filepath):
        os.remove(filepath)
    pil_img.save(filepath, format='jpeg')

    return buffer.getvalue()


def seek():
    global vs
    if vs is None:
        return None

    return vs.seek()


def camera_stop():
    global vs
    if vs is not None:
        vs.stop()


class Camera(Resource):
    def get(self):
        print('Camera.get()')

        img: bytes = capture_image()

        if img is None:
            return {'message': 'sorry, cant collect camera image.'}

        # response base64 encoded jpeg image data
        data: dict = {
            'timestamp': datetime.datetime.now(tz=utc).timestamp(),
            'data': base64.b64encode(img).decode(encoding='utf-8')
        }
        print(str(data)[0:100])

        return data


class CPU(Resource):
    def get(self):
        print('CPU.get()')

        data: dict = {
            'timestamp': datetime.datetime.now(tz=utc).timestamp(),
            'data': {
                'cpu_clock': get_cpu_clock(),
                'cpu_temp': get_cpu_temp()
            }
        }
        print(str(data)[0:100])

        return data


class TemperatureAndHumidity(Resource):
    def get(self):
        print(f'TemperatureAndHumidity.get()')

        data: dict = None
        room_temp = get_temperature_and_humidity()
        if room_temp is not None and room_temp.is_valid():
            data = {
                'timestamp': datetime.datetime.now(tz=utc).timestamp(),
                'data': {
                    'room_temperature': room_temp.temperature,
                    'room_humidity': room_temp.humidity
                }
            }
        else:
            data = {
                'timestamp': datetime.datetime.now(tz=utc).timestamp(),
                'data': {
                    'room_temperature': 'N/A',
                    'room_humidity': 'N/A'
                }
            }

        print(str(data)[0:100])

        return data


@app.route('/camera/current.jpg')
def current_img():
    print('current_img()')
    # response jpeg image
    img: bytes = capture_image()
    if img is None:
        return Response('sorry, cant collect camera image.', status=503)

    return Response(img, mimetype='image/jpeg')


@app.route('/')
def index():
    print('index()')
    temp = get_cpu_temp()
    clock = get_cpu_clock()

    room_temp = 'N/A'
    room_humidity = 'N/A'
    tempandhumid = get_temperature_and_humidity()
    if tempandhumid is not None and tempandhumid.is_valid():
        room_temp = tempandhumid.temperature
        room_humidity = tempandhumid.humidity

    return render_template("index.html",
                           cpu_temp=temp, cpu_clock=clock,
                           room_temperature=room_temp, room_humidity=room_humidity)


def get_cpu_temp() -> float:
    print('get_cpu_temp()')
    try:
        cmd = ["vcgencmd", "measure_temp"]
        res = subprocess.check_output(cmd)
        temp = res.decode(encoding='utf-8').split('=')
        temp_num = float(temp[1].replace("'C", ""))
        return temp_num
    except Exception as e:
        print(e)
        return 'N/A'


def get_cpu_clock() -> float:
    print('get_cpu_clock()')
    try:
        cmd = ["vcgencmd", "measure_clock", "arm"]
        res: bytes = subprocess.check_output(cmd)
        res = res.decode(encoding='utf-8').split('=')
        clock_num = float(res[1])
        clock_num = clock_num / (1000*1000)
        return clock_num
    except Exception as e:
        print(e)
        return 'N/A'


def get_temperature_and_humidity():
    print('get_temperature_and_humidity()')
    try:
        with dht_lock:
            temperature = dht_device.temperature
            humidity = dht_device.humidity
        return DHTReading(temperature, humidity)

    except RuntimeError as e:
        print(e)
    except Exception as e:
        print(e)
    return None


def server_thread():
    print('server_thread()')
    api.add_resource(Camera, '/api/camera/')
    api.add_resource(CPU, '/api/cpu/')
    api.add_resource(TemperatureAndHumidity, '/api/temperatureandhumidity')
    app.run(host='0.0.0.0', port=5000)


def start_server_thread():
    print('start_server_thread()')
    threading.Thread(target=server_thread, args=()).start()


if __name__ == "__main__":

    print(f'start __main__')

    try:
        start_server_thread()
        vs = PiVideoStream((1024, 768), 10)
        vs.start()
        while True:
            # メインスレッドでapp.run()すると、flaskによって？作られた
            # 別プロセス？でもう一度PiVideoStreamのinitが呼ばれてしまう。
            # メインスレッドで起動しているPiVideoStreamによってPicamera2はすでにopenされているので
            # flask側で作られたPiVideoStreamはカメラにアクセスできない。
            # flaskを明示的に別スレッドで立ち上げることでflaskのよくわからない別プロセスが起動するのを
            # 抑止できたのでとりあえずの回避策とする。
            sleep(1)
    except Exception as e:
        print(e)
    finally:
        camera_stop()
        dht_device.exit()
