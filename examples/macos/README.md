# LibPeer Unity Sample (macOS)

DataChannel サンプル - `examples/generic/main.c` と同等の機能を Unity で実装

## セットアップ

### 1. Unity でプロジェクトを開く

```bash
# Unity Hub からプロジェクトを開く
# または Unity Editor で直接開く
open -a Unity LibPeerSample
```

**注意**: 初回起動時に Unity がプロジェクトを初期化します。

### 2. シーンを作成

1. `File > New Scene` で新しいシーンを作成
2. `Assets/Scenes/SampleScene.unity` として保存
3. 空の GameObject を作成 (`Create Empty`)
4. `LibPeerSample` スクリプトをアタッチ

### 3. UI を作成 (オプション)

1. `GameObject > UI > Canvas` を作成
2. 以下の UI 要素を追加:
   - `InputField` (URL 入力用)
   - `Button` x2 (Connect / Disconnect)
   - `Text` x2 (Status / Log)
3. `LibPeerSample` コンポーネントにドラッグ&ドロップ

## 使い方

### SFU サーバーの起動

```bash
# ローカルで SFU を起動 (ポート 8888)
cd /path/to/sfu
./sfu

# 別ターミナルで cloudflared tunnel を起動
cloudflared tunnel --url http://127.0.0.1:8888
# => https://xxx-xxx-xxx.trycloudflare.com のような URL が表示される
```

### Unity で接続

1. Unity Editor でプレイモードを開始
2. 表示された cloudflared URL を入力フィールドにペースト
   - 例: `https://neo-pin-dat-revised.trycloudflare.com`
3. `Connect` ボタンをクリック
4. 接続が確立されると自動的に1秒ごとにメッセージを送信

## 動作確認

接続成功時のログ:
```
[12:34:56] Connecting to: https://xxx.trycloudflare.com
[12:34:56] Signaling connected
[12:34:57] State: checking
[12:34:57] State: connected
[12:34:57] State: completed
[12:34:57] DataChannel opened
[12:34:58] Sent: datachannel message : 00000
[12:34:59] Sent: datachannel message : 00001
```

`ping` を受信すると自動的に `pong` を返します。

## ビルド

```bash
# macOS スタンドアロンビルド
# Unity Editor: File > Build Settings > macOS > Build
```

## トラブルシューティング

### libpeer.bundle が見つからない

```
DllNotFoundException: peer
```

→ UPM パッケージが正しくインポートされているか確認:
- `Packages/manifest.json` に `jp.co.mixi.libpeer` があるか
- `Packages/jp.co.mixi.libpeer/Plugins/macOS/libpeer.bundle` が存在するか

### 接続できない

- cloudflared tunnel が起動しているか確認
- SFU サーバーがポート 8888 で起動しているか確認
- HTTPS URL が正しいか確認
