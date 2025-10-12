# Raspberry Pi Camera RTMP Streamer

このスクリプトは、Raspberry Piのカメラから`rpicam-vid`と`ffmpeg`を使用してRTMPサーバーにビデオをストリーミングします。

ストリームには、カスタムテキストメッセージと現在のタイムスタンプがオーバーレイとして追加されます。

## 依存関係

- `libcamera-apps`: `rpicam-vid`コマンドを提供します。
- `ffmpeg`: ビデオの処理とストリーミングに使用します。

## 設定

スクリプトの冒頭にある以下の変数を編集することで、動作をカスタマイズできます。

- `RTMP_URL`: RTMPサーバーのURL。
- `WIDTH`, `HEIGHT`: カメラキャプチャの解像度。
- `FRAMERATE`: ビデオストリームのフレームレート。
- `MESSAGE`: ビデオにオーバーレイ表示するテキストメッセージ。
- `FILTER_SCALE`: スケーリング後の出力解像度 (例: `"scale=1280:720"`)。
- `FONT_PATH`: オーバーレイテキストに使用するフォントファイルのパス。

## 使い方

1. スクリプトに実行権限を付与します。
   ```bash
   chmod +x rpi-camera-streamer.sh
   ```

2. スクリプトを実行します。
   ```bash
   ./rpi-camera-streamer.sh
   ```

スクリプトは、停止されるまで（例: `Ctrl+C`）、ビデオフィードを継続的にストリーミングします。
