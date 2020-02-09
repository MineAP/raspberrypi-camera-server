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

from flask import Flask, Response, render_template
from flask_restful import Api, Resource
from PIL import Image
from pytz import utc

import RPi.GPIO as GPIO
from DHT22_Python.dht22 import DHT22
from picamera import PiCamera
from picamera.array import PiRGBArray

'''
Flaskを使ったRaspberryPi Camera画像配信サーバー
'''

app: Flask = Flask(__name__)
api: Api = Api(app)
vs = None

# initialize GPIO
GPIO.setwarnings(True)
GPIO.setmode(GPIO.BCM)

# read data using pin 4
instance = DHT22(pin=4)


class PiVideoStream:
    '''
    バックグラウンドで動く画像収集ストリーム
    https://research.itplants.com/?p=1562
    '''

    def __init__(self, resolution=(320, 240), framerate=32):
        print(f'PiVideoStream.__init__()')
        # initialize the camera and stream
        self.camera = PiCamera()
        self.camera.resolution = resolution
        self.camera.framerate = framerate
        self.rawCapture = PiRGBArray(self.camera, size=resolution)
        self.stream = self.camera.capture_continuous(
            self.rawCapture, format="bgr", use_video_port=True)
        self.stopped = False

        # initialize the frame and the variable used to indicate
        # if the thread should be stopped
        self.frame = None
        self.stopped = False
        #self.camera.resolution = (640, 480)
        #self.camera.framerate = 32
        self.camera.sharpness = 0
        self.camera.contrast = 0
        self.camera.brightness = 50
        self.camera.saturation = 0
        self.camera.ISO = 0
        self.camera.video_stabilization = False
        self.camera.exposure_compensation = 0
        #self.camera.exposure_mode = 'off'
        self.camera.awb_mode = 'flash'
        self.camera.meter_mode = 'average'
        self.camera.image_effect = 'none'
        self.camera.color_effects = None
        self.camera.rotation = 0
        self.camera.hflip = True
        self.camera.vflip = True
        self.camera.crop = (0.0, 0.0, 1.0, 1.0)

    def start(self):
        print(f'PiVideoStream.start()')
        # start the thread to read frames from the video stream
        threading.Thread(target=self.update, args=()).start()
        return self

    def update(self):
        # keep looping infinitely until the thread is stopped
        for f in self.stream:
            # grab the frame from the stream and clear the stream in
            # preparation for the next frame
            self.frame = f.array
            self.rawCapture.truncate(0)

            # if the thread indicator variable is set, stop the thread
            # and resource camera resources
            if self.stopped:
                self.stream.close()
                self.rawCapture.close()
                self.camera.close()
                return

    def read(self):
        # return the frame most recently read
        return self.frame

    def stop(self):
        print(f'PiVideoStream.stop()')
        # indicate that the thread should be stopped
        self.stopped = True

    def seek(self):
        self.rawCapture.seek(-1, 2)


def capture():
    global vs
    return vs.read()


def capture_image() -> bytes:
    '''
    convert narray to jpeg binary
    '''

    pil_img: Image = Image.fromarray(capture())
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
    return vs.seek()


def camera_stop():
    global vs
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
        result = instance.read()
        return result

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
            # メインスレッドで起動しているPiVideoStreamによってPiCameraはすでにopenされているので
            # flask側で作られたPiVideoStreamはカメラにアクセスできない。
            # flaskを明示的に別スレッドで立ち上げることでflaskのよくわからない別プロセスが起動するのを
            # 抑止できたのでとりあえずの回避策とする。
            sleep(1)
    except Exception as e:
        print(e)
    finally:
        camera_stop()
        GPIO.cleanup()
