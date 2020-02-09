# FlaskによるRaspberryPi Camera サーバー

FlaskとFlask-RESTfulを使ったラズパイカメラの画像をHTTPで公開するサーバー

## 想定環境

### ハードウェア

- RaspberryPi 4
- RasPi Camera V2.1
- DHT22 (温湿度センサー)
  - GPIO 4ピンにDATA線が接続されていることを想定

### ソフトウェア

- Raspbian GNU/Linux 10 (buster)
- Python 3.7
  
## 依存モジュール

### pip3

- Flask==1.1.1
- Flask-RESTful==0.3.7
- picamera==1.13
- Pillow==7.0.0
- RPi.GPIO=0.7.0

### git submodule

- https://github.com/MineAP/DHT22_Python

## 起動方法

    > python3 camera-server.py

## 使い方

### 現在のカメラ画像を見る

ウェブブラウザで以下のURLを開くとJPEG画像が表示される

    http://raspberrypi.local:5000

### JSON形式で画像を取得する

以下のURLに対してHTTP GETリクエストを投げる

    http://raspberrypi.local:5000/api/camera/

タイムスタンプとBase64エンコードされたjpeg画像が得られる

    {
        "timestamp": 1580553676.777748,
        "data": "/9j/4AAQSkZJRgABAQ..."
    }

### JSON形式でCPUのクロック情報と温度を取得する

以下のURLに対してHTTP GETリクエストを投げる

    http://raspberrypi.local:5000/api/cpu/

タイムスタンプとCPUクロック、温度が得られる

    {
        "timestamp": 1580630488.874677, 
        "data": {
            "cpu_clock": 750.199232, 
            "cpu_temp": 37.0
        }
    }

### JSON形式で室内の温度と湿度を取得する

以下のURLに対してHTTP GETリクエストを投げる

    http://raspberrypi.local:5000/api/temperatureandhumidity

タイムスタンプと温度、湿度が得られる。

    {
        "timestamp": 1581223396.671932, 
        "data": {
            "room_temperature": 22.3, 
            "room_humidity": 26.6
        }
    }

