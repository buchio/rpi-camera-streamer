# Raspberry Pi カメラストリーマー

Raspberry Piのカメラモジュールまたは標準的なUSBウェブカメラからのビデオを、ローカルネットワーク経由でストリーミングするためのシンプルなPythonスクリプトです。

## 概要

このプロジェクトは、ライブビデオをMJPEGフィードとしてストリーミングするWebサーバーを作成する単一のスクリプト (`main.py`) を提供します。Raspberry Piで実行するように設計されており、公式のCSIカメラモジュールまたは汎用のUSBウェブカメラのいずれかを使用するように設定できます。ストリームは、同一ネットワーク上の任意のWebブラウザからアクセスできます。

## 主な機能

-   **デュアルカメラ対応**: Raspberry Piカメラモジュール (`picamera2`経由) とUSBウェブカメラ (`OpenCV`経由) の両方で動作します。
-   **Webベースのストリーミング**: ビデオをMJPEGフィードとしてストリーミングし、Webブラウザで表示できます。
-   **タイムスタンプオーバーレイ**: 現在の日時をビデオフレームに自動的にオーバーレイ表示します。
-   **設定可能**: カメラの種類、ポート、解像度、FPS、品質など、すべての主要なパラメータをコマンドライン引数で設定できます。
-   **軽量**: Pythonの標準ライブラリ `http.server` を使用しており、依存関係は最小限です。

## 要件

-   Python 3
-   Raspberry Pi
-   接続されたカメラ (Raspberry PiカメラモジュールまたはUSBウェブカメラ)

## インストール

pipを使用して必要なPythonライブラリをインストールします。

**コア依存関係 (両方のカメラタイプで共通):**

```bash
pip install opencv-python
```

**Raspberry Piカメラモジュールのサポート (`--camera-type rpi`):**

`picamera2` ライブラリもインストールする必要があります。

```bash
pip install picamera2
```
*注意: `picamera2` は通常、Bullseye以降のリリースのRaspberry Pi OS (32ビットまたは64ビット) でのみ利用可能です。*


## 使い方

`main.py` スクリプトに、必須の `--camera-type` 引数を付けて実行します。

#### Raspberry Piカメラモジュールからストリーミングする場合:

1.  カメラモジュールをRaspberry PiのCSIポートに接続します。
2.  スクリプトを実行します:
    ```bash
    python3 main.py --camera-type rpi
    ```
3.  Webブラウザを開き、 `http://<あなたのPiのIPアドレス>:8080` にアクセスします。

#### USBウェブカメラからストリーミングする場合:

1.  USBカメラをRaspberry PiのUSBポートのいずれかに接続します。
2.  スクリプトを実行します:
    ```bash
    python3 main.py --camera-type usb
    ```
3.  Webブラウザを開き、 `http://<あなたのPiのIPアドレス>:8080` にアクセスします。

### コマンドライン引数

以下の引数を使用してストリームをカスタマイズできます:

```
usage: main.py [-h] --camera-type {rpi,usb} [--port PORT] [--width WIDTH] [--height HEIGHT] [--fps FPS] [--quality QUALITY] [--device-id DEVICE_ID] [--message MESSAGE]

Raspberry Pi用の統合カメラストリーマー。

options:
  -h, --help            このヘルプメッセージを表示して終了します
  --camera-type {rpi,usb}
                        使用するカメラの種類。
  --port PORT           Webサーバーのポート。(デフォルト: 8080)
  --width WIDTH         フレームの幅。(デフォルト: 640)
  --height HEIGHT       フレームの高さ。(デフォルト: 480)
  --fps FPS             フレームレート。(デフォルト: 15)
  --quality QUALITY     JPEGの品質 (1-100)。(デフォルト: 70)
  --device-id DEVICE_ID
                        USBカメラのデバイスID。(デフォルト: 0)
  --message MESSAGE     ストリームに表示するメッセージ。(デフォルト: RPi Camera または USB Camera)
```
**カスタムパラメータを指定した例:**
```bash
python3 main.py --camera-type usb --port 8000 --width 1280 --height 720 --fps 30
```
