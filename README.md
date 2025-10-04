# WebSocket リアルタイムメディアストリーマー

Raspberry Piに接続されたカメラモジュールまたはUSBウェブカメラからの映像と音声を、WebSocketを使用して低遅延でリアルタイムにストリーミングするためのアプリケーションです。

## 概要

このプロジェクトは、映像と音声の各データに高精度なタイムスタンプを付与し、単一のWebSocketストリームで配信するPythonサーバーを起動します。クライアント（Webブラウザ）側は、受け取ったデータをJavaScriptで処理し、映像の描画と音声の再生を動的に行います。プログラムからタイムスタンプ付きのデータを直接利用したい開発用途に適しています。

## 主な機能

-   **WebSocketベースのストリーミング**: HTTPストリーミングに比べ、より低遅延でリアルタイム性の高い通信を実現します。
-   **タイムスタンプ埋め込み**: 映像・音声の各データパケットにUNIXタイムスタンプが付与され、プログラムでの同期処理や分析に利用できます。
-   **デュアルカメラ対応**: Raspberry Piカメラモジュール (`picamera2`経由) とUSBウェブカメラ (`OpenCV`経由) の両方で動作します。
-   **音声ストリーミング**: マイクが接続されていれば、映像と同時に音声もストリーミングできます (`sounddevice`経由)。
-   **モダンなクライアント**: 受信したデータを動的に処理する、単一ページのJavaScriptアプリケーションとして動作します。

## 依存関係のインストール

pipを使用して、必要なPythonライブラリをインストールします。

```bash
pip install Flask flask-sock opencv-python numpy sounddevice
```

#### Raspberry Piカメラモジュールを使用する場合

上記に加えて `picamera2` ライブラリもインストールする必要があります。

```bash
pip install picamera2
```
*注意: `picamera2` は通常、Bullseye以降のリリースのRaspberry Pi OSでのみ利用可能です。*

## 実行方法

`main.py` スクリプトに、必須の `--camera-type` 引数を付けて実行します。サーバーは単一のポートで、映像・音声・Webページのすべてを配信します。

#### Raspberry Piカメラからストリーミング (映像と音声)

```bash
python3 main.py --camera-type rpi --enable-audio
```

#### USBウェブカメラからストリーミング (映像と音声)

```bash
python3 main.py --camera-type usb --enable-audio
```

スクリプト起動後、Webブラウザで `http://<あなたのPiのIPアドレス>:8080` にアクセスしてください。

**注意:** 初回アクセス時、音声の再生を開始するには、ブラウザの自動再生ポリシーにより、画面に表示される「Click to Start Audio」というメッセージをクリックする必要があります。

## 開発者向け情報: データフォーマット

WebSocket (`/stream`) を通じて、サーバーからクライアントへ以下の形式のテキストメッセージが送信されます。

```
<type>:<timestamp>:<data>
```

-   **`<type>`**: データの種類。`video` または `audio` のいずれか。
-   **`<timestamp>`**: データがサーバーでキャプチャされたUNIXタイムスタンプ (浮動小数点数)。
-   **`<data>`**: メディアデータをBase64エンコードした文字列。
    -   `video`の場合: JPEG画像データ
    -   `audio`の場合: 16ビット符号付き整数・リトルエンディアンの生PCMデータ

## コマンドライン引数

```
usage: main.py [-h] --camera-type {rpi,usb} [--port PORT] [--host HOST] [--width WIDTH] [--height HEIGHT] [--fps FPS] [--quality QUALITY] [--device-id DEVICE_ID] [--enable-audio]
               [--audio-device AUDIO_DEVICE] [--audio-channels AUDIO_CHANNELS] [--audio-samplerate AUDIO_SAMPLERATE]

WebSocket Media Streamer

options:
  -h, --help            show this help message and exit
  --camera-type {rpi,usb}
                        Type of camera to use.
  --port PORT
  --host HOST
  --width WIDTH
  --height HEIGHT
  --fps FPS
  --quality QUALITY
  --device-id DEVICE_ID
                        USB camera device ID.
  --enable-audio
  --audio-device AUDIO_DEVICE
                        Audio input device index.
  --audio-channels AUDIO_CHANNELS
                        Number of audio channels (1=mono).
  --audio-samplerate AUDIO_SAMPLERATE
                        Audio sample rate in Hz. Defaults to device default.
```
