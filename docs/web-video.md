# 動画再生 (VideoOverlay)

wasm ではデコーダ (libvpx など) を移植せず、**ブラウザの `<video>` 要素**にデコード・音声の出力・同期を
任せます (core 側の `sdl3/base/WebMoviePlayer.cpp`)。ブラウザが再生できる形式 (webm/VP8/VP9/AV1、環境に
よっては mp4/H.264) が対象です。

- **mixer / overlay モード**: `<video>` を DOM のオーバーレイとして canvas に重ねて表示します (ウィンドウに
  内接するフィット・中央寄せ = デスクトップ SDL の実装と同じ見た目)。`pointer-events: none` なので入力は
  エンジンにそのまま渡り、ムービー中のクリックでのスキップなどがそのまま動きます
- **layer モード**: 非表示の `<video>` + requestVideoFrameCallback でフレームを RGBA で取得し、通常の
  レイヤの描画に合成します (デスクトップと同じ `layer1` / `layer2` の API)
- **ソース**: `web://` / `webnc://` は URL を直接 `<video>` に渡します (**ストリーミング再生**。fetch / OPFS
  を通らず、メモリに全て展開しません。シークは HTTP Range を使います — serve.py は対応済みです。本番のサーバ
  も Range に対応しているのが望ましいです)。MEMFS / xp3 アーカイブの中のファイルは全て読んで Blob URL で
  再生します (大きい動画は xp3 に入れず、web:// 側に置いてください)
- 状態の遷移は `onStatusChanged("play"/"stop")` で通知されます (再生が終わると stop)。音量は `audioVolume`
  が `<video>` の volume に対応します
- 注意: ブラウザの autoplay ポリシーで、ユーザの操作より前の音声付きの再生は拒否されることがあります
  (その場合は、次のクリック / キー入力で自動で再試行します)
