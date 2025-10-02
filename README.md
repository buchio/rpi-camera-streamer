# Raspberry Pi カメラストリーマー

Raspberry Piに接続されたカメラモジュールまたはUSBウェブカメラからの映像と音声を、ネットワーク経由でストリーミングするためのFlaskベースのアプリケーションです。

## 概要

このプロジェクトは、ライブビデオをMJPEGフィードとして、音声をWAVストリームとして提供するWebサーバーを起動する、単一のPythonスクリプト (`main.py`) です。公式のCSIカメラモジュールと汎用のUSBウェブカメラの両方をサポートしており、コマンドラインオプションで簡単に切り替えられます。

## 主な機能

-   **デュアルカメラ対応**: Raspberry Piカメラモジュール (`picamera2`経由) とUSBウェブカメラ (`OpenCV`経由) の両方で動作します。
-   **音声ストリーミング**: マイクが接続されていれば、映像と同時に音声をストリーミングできます (`sounddevice`経由)。
-   **Webベースのストリーミング**: 同一ネットワーク上の任意のWebブラウザから映像と音声にアクセスできます。
-   **タイムスタンプオーバーレイ**: 現在の日時をビデオフレームに自動的にオーバーレイ表示します。
-   **設定可能**: カメラの種類、ポート、解像度、FPS、品質など、多くのパラメータをコマンドライン引数で設定できます。

## 依存関係のインストール

pipを使用して必要なPythonライブラリをインストールします。

#### コア依存関係 (必須)

```bash
pip install Flask opencv-python numpy
```

#### Raspberry Piカメラモジュールを使用する場合

`picamera2` ライブラリもインストールする必要があります。

```bash
pip install picamera2
```
*注意: `picamera2` は通常、Bullseye以降のリリースのRaspberry Pi OSでのみ利用可能です。*

#### 音声ストリーミングを有効にする場合

`sounddevice` と `soundfile` ライブラリが必要です。

```bash
pip install sounddevice soundfile
```

#### オーディオのデバッグ用ツール (推奨)

問題解決のために、ALSAのユーティリティをインストールしておくことを強くお勧めします。

```bash
sudo apt-get update
sudo apt-get install alsa-utils
```

## 実行方法

`main.py` スクリプトに、必須の `--camera-type` 引数を付けて実行します。サーバーはデフォルトでネットワーク上のすべてのインターフェースで待機します。

#### Raspberry Piカメラからストリーミング (映像のみ)

```bash
python3 main.py --camera-type rpi --port 8080
```

#### Raspberry Piカメラからストリーミング (映像と音声)

1.  マイクをRaspberry Piに接続します。
2.  `--enable-audio` フラグを付けてスクリプトを実行します。
    ```bash
    python3 main.py --camera-type rpi --port 8080 --enable-audio
    ```

#### USBウェブカメラからストリーミング (映像と音声)

1.  USBカメラとマイクを接続します。
2.  `--enable-audio` フラグを付けてスクリプトを実行します。
    ```bash
    python3 main.py --camera-type usb --port 8080 --enable-audio
    ```

スクリプト起動後、Webブラウザで `http://<あなたのPiのIPアドレス>:8080` にアクセスしてください。音声が有効な場合、ページにオーディオプレーヤーが表示されます。

すべてのオプションを確認するには `python3 main.py --help` を実行してください。

## オーディオのトラブルシューティング

音声が聞こえない、またはスクリプトでエラーが出る場合の一般的な原因と解決策です。

### 1. デバイスが認識されない

`No audio input devices found` や `Error querying device -1` といったエラーが出る場合、システムがマイクを認識できていません。

#### a) 権限の確認

サウンドデバイスにアクセスするには、ユーザーが `audio` グループに所属している必要があります。

**① 所属グループの確認:**
以下のコマンドで、現在のユーザーが `audio` グループにいるか確認します。
```bash
groups
```
出力に `audio` が含まれていない場合、権限がありません。

**② グループへの追加:**
以下のコマンドで、現在のユーザーを `audio` グループに追加します。
```bash
sudo usermod -a -G audio $USER
```

**重要:** この変更を有効にするには、一度**ログアウトしてから再度ログイン**するか、システムを**再起動**する必要があります。

#### b) ハードウェアの確認

OSがハードウェア自体を認識しているか確認します。

**① 録音デバイスのリスト表示:**
`arecord` コマンドで、ALSAが認識している録音デバイスの一覧を表示します。
```bash
arecord -l
```
このコマンドで「サウンドカードが見つかりません」と表示されたり、お使いのマイクが含まれていなかったりする場合、OSレベルでデバイスが認識されていません。ドライバの問題やハードウェアの互換性の問題が考えられます。

### 2. 音が小さい、または聞こえない

デバイスは認識されているが音声がストリーミングされない場合、マイクがミュート（消音）になっているか、入力音量が小さすぎる可能性があります。

**① alsamixerの起動:**
`alsamixer` を使って、サウンドデバイスの設定を対話的に変更できます。
```bash
alsamixer
```

**② デバイスの選択と設定:**
-   `F6` キーを押して、お使いのUSBマイクを選択します。
-   矢印キー（↑, ↓）で入力音量（Captureボリューム）を調整します。
-   `M` キーを押して、ミュート（`MM`と表示される）とミュート解除（`OO`と表示される）を切り替えます。
-   `Esc` キーで終了します。

## コマンドライン引数

```
usage: main.py [-h] --camera-type {rpi,usb} [--port PORT] [--host HOST] [--message MESSAGE] [--width WIDTH] [--height HEIGHT] [--fps FPS] [--quality QUALITY]
               [--device-id DEVICE_ID] [--enable-audio] [--audio-samplerate AUDIO_SAMPLERATE] [--audio-channels AUDIO_CHANNELS] [--audio-duration AUDIO_DURATION]

Unified camera streamer for Raspberry Pi using Flask.

options:
  -h, --help            show this help message and exit
  --camera-type {rpi,usb}
                        Type of camera to use.
  --port PORT           Port for the web server.
  --host HOST           Host address for the web server.
  --message MESSAGE     Message to display on stream.
  --width WIDTH         Frame width.
  --height HEIGHT       Frame height.
  --fps FPS             Frames per second.
  --quality QUALITY     JPEG quality (1-100).
  --device-id DEVICE_ID
                        USB camera device ID.
  --enable-audio        Enable audio streaming.
  --audio-samplerate AUDIO_SAMPLERATE
                        Audio sample rate in Hz.
  --audio-channels AUDIO_CHANNELS
                        Number of audio channels.
  --audio-duration AUDIO_DURATION
                        Audio chunk duration in ms.
```