# FlaskによるRaspberryPi Camera サーバー

FlaskとFlask-RESTfulを使ったラズパイカメラの画像をHTTPで公開するサーバー

## 想定環境

- RaspberryPi 4
- RasPi Camera V2.1
- Python 3.7
  
## 依存モジュール

- Flask==1.1.1
- Flask-RESTful==0.3.7
- picamera==1.13
- Pillow==7.0.0

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