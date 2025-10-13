# 高機能 Raspberry Pi RTMP ストリーマー

このスクリプトは、Raspberry PiのカメラモジュールやUSBカメラ、マイクからの映像・音声を柔軟に組み合わせてRTMPサーバーにストリーミングします。

## 主な機能

-   **4つの動作モード:**
    1.  **映像 & 音声:** USBカメラとマイクからのストリーミング。
    2.  **音声のみ:** マイクからの音声のみのストリーミング。
    3.  **映像のみ (USBカメラ):** USBカメラからの映像のみのストリーミング。
    4.  **映像のみ (Piカメラ):** Raspberry Pi標準カメラモジュールからの映像のみのストリーミング。
-   **動的設定:** 実行するホスト名に応じた設定ファイルを自動で読み込みます。
-   **映像オーバーレイ:** 映像にテキストファイルの内容やタイムスタンプを焼き込む機能（設定による）。
-   **systemd対応:** systemdサービスとしてバックグラウンドで安定稼働させるためのテンプレートを同梱。

## 依存関係

-   `libcamera-apps`: Piカメラモードで使用 (`rpicam-vid`)。
-   `ffmpeg`: すべてのモードで中核となるエンコードとストリーミングに使用。
-   `alsa-utils`: マイクを使用するモードで必要。

## 設定方法

1.  **設定ディレクトリの準備:**
    スクリプトと同じ階層に `settings` ディレクトリを作成します。

2.  **ホスト別設定ファイルの作成:**
    `settings` ディレクトリ内に、`$(hostname).sh` という名前のファイルを作成します（例: `rasp3-ubuntu-3.sh`）。このファイルに、動作モードを決定する変数を記述します。

    **設定例:**

    -   **映像 & 音声モード:**
        ```bash
        VIDEO_DEVICE="/dev/video0"
        AUDIO_DEVICE="plughw:1,0"
        WIDTH=854
        HEIGHT=480
        FRAMERATE=5
        ```

    -   **音声のみモード:**
        ```bash
        AUDIO_DEVICE="plughw:1,0"
        ```

    -   **映像のみ (USBカメラ) モード:**
        ```bash
        VIDEO_DEVICE="/dev/video0"
        WIDTH=1280
        HEIGHT=720
        FRAMERATE=10
        ```

    -   **映像のみ (Piカメラ) モード:**
        （設定ファイルに何も書かないか、`VIDEO_DEVICE`と`AUDIO_DEVICE`を空にします）
        ```bash
        WIDTH=1920
        HEIGHT=1080
        FRAMERATE=10
        ```

3.  **スクリプト本体の編集:**
    `rpi-camera-streamer.sh` を開き、`RTMP_URL` をご自身の環境に合わせて設定してください。

## 実行方法

### 手動実行

```bash
# スクリプトは ffmpeg/ ディレクトリにあると仮定
cd ffmpeg/
chmod +x rpi-camera-streamer.sh
./rpi-camera-streamer.sh
```

### systemdサービスとして実行

1.  `ffmpeg/systemd/rpi-camera-streamer.service` ファイルを編集し、`__USER__` と `__PATH_TO_PROJECT__` をご自身の環境に合わせます。
2.  編集したファイルを `/etc/systemd/system/` にコピーします。
    ```bash
    sudo cp ffmpeg/systemd/rpi-camera-streamer.service /etc/systemd/system/
    ```
3.  サービスを有効化して起動します。
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable rpi-camera-streamer.service
    sudo systemctl start rpi-camera-streamer.service
    ```

---

## Python MJPEG Streamer (代替手段)

このプロジェクトには、`ffmpeg`を使ったRTMPストリーミングの代替として、Pythonで実装されたMJPEGストリーマーも含まれています。これは、Webブラウザで直接表示できるHTTPベースのストリーミングを提供します。

### 機能

-   Raspberry Piカメラ (`picamera2`) とUSBカメラ (`OpenCV`) の両方をサポート。
-   低遅延なMJPEG形式でストリーミング。
-   映像にタイムスタンプとカスタムメッセージをオーバーレイ描画。
-   解像度、フレームレート、JPEG品質などを柔軟に設定可能。

### 依存関係 (Python)

-   `opencv-python`
-   `picamera2` (Piカメラを使用する場合)

```bash
# 必要なライブラリをインストール
pip install opencv-python
# Piカメラを使用する場合は以下もインストール
pip install picamera2
```

### 使い方

1.  **USBカメラでストリーミング:**
    ```bash
    # python/ ディレクトリに移動
    cd python/
    # USBカメラ(デバイス0)を640x480, 15fpsでストリーミング
    python3 main.py --camera-type usb --width 640 --height 480 --fps 15
    ```

2.  **Piカメラでストリーミング:**
    ```bash
    # python/ ディレクトリに移動
    cd python/
    # Piカメラを1280x720, 10fpsでストリーミング
    python3 main.py --camera-type rpi --width 1280 --height 720 --fps 10
    ```

3.  **ブラウザで表示:**
    スクリプトを実行すると、コンソールにURLが表示されます（例: `http://<IPアドレス>:8080`）。このURLにWebブラウザでアクセスしてください。

### コマンドラインオプション

-   `--camera-type`: `rpi` または `usb` を指定 (必須)。
-   `--port`: Webサーバーのポート (デフォルト: 8080)。
-   `--width`, `--height`: 解像度 (デフォルト: 640x480)。
-   `--fps`: フレームレート (デフォルト: 15)。
-   `--quality`: JPEG品質 (1-100, デフォルト: 70)。
-   `--device-id`: USBカメラのデバイスID (デフォルト: 0)。
-   `--message`: オーバーレイ表示するメッセージ。
