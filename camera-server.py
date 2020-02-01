import base64
import datetime
import json
import threading
import traceback
from io import BytesIO
from queue import Queue
from time import sleep

from flask import Flask, Response, render_template
from flask_restful import Api, Resource
from PIL import Image

from picamera import PiCamera
from picamera.array import PiRGBArray

'''
Flaskを使ったRaspberryPi Camera画像配信サーバー
'''

app:Flask = Flask(__name__)
api:Api = Api(app)
vs = None

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
        self.stream = self.camera.capture_continuous(self.rawCapture, format="bgr", use_video_port=True)
        self.stopped=False
 
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
        self.rawCapture.seek(-1,2)

def capture():
    global vs
    return vs.read()

def capture_image() -> bytes:
    '''
    convert narray to jpeg binary
    '''

    pil_img:Image = Image.fromarray(capture())
    buffer = BytesIO()
    pil_img.save(buffer, format='jpeg')

    # save image file for debug
    pil_img.save('./tmp.jpeg', format='jpeg')

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

        img:bytes = capture_image()

        if img is None:
            return {'message' : 'sorry, cant collect camera image.'}

        # response base64 encoded jpeg image data
        data:dict = {
            'timestamp': datetime.datetime.now().timestamp(),
            'data': base64.b64encode(img).decode(encoding='utf-8')
        }
        print(str(data)[0:100])
        
        return data


@app.route('/camera/current.jpg')
def current_img():
    # response jpeg image
    img:bytes = capture_image()
    print(type(img))
    return Response(img, mimetype='image/jpeg')


@app.route('/')
def index():
    return render_template("index.html")


def server_thread():
    print('server_thread()')
    api.add_resource(Camera, '/api/camera/')
    app.run(host='0.0.0.0', port=5000)


def start_server_thread():
    print('start_server_thread()')
    threading.Thread(target=server_thread, args=()).start()


if __name__ == "__main__":
    
    print(f'start __main__')

    try:
        start_server_thread()
        vs = PiVideoStream((640,480),5)
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