# whisper-tamas-ui - EXE ビルド手順

## 概要

このプロジェクトは `build.ps1` を使って `WhisperTamas.exe` を生成します。  
ビルド後の成果物は `dist\WhisperTamas\` に出力されます。  
このドキュメントはメンテナンス向けのビルド手順を扱います。通常利用者向けの導入や使い方は `README.md` にまとめます。

## 責務の分離

- `README.md`: 利用者向けの最短導入手順、基本的な使い方、設定の意味
- `EXE_BUILD.md`: 開発者 / 公開担当向けのビルド方法、成果物確認、配布前チェック
- `dist\`: ローカルで生成されるビルド成果物。公開用リリースそのものではなく、配布前の確認対象

## 前提

- Windows
- Python 3.11 以上
- 仮想環境 `.venv` を作成済み

## 初回セットアップ

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

## 動作確認

EXE 化の前に、まず通常実行で確認します。

```powershell
python main.py
```

確認ポイント:

- モデルロードが成功する
- トレイメニューが表示される
- `alt+q` / `alt+w` が動作する
- `config.toml` の変更が反映される

## ビルド

```powershell
.\build.ps1
```

このスクリプトは以下を行います。

- `whisper-tamas-ui.spec` を使って PyInstaller を実行
- `dist\WhisperTamas\WhisperTamas.exe` を生成
- `config.toml` を成果物フォルダへコピー
- `install_startup.ps1` / `uninstall_startup.ps1` を成果物フォルダへコピー

## 出力構成

```text
dist/
└─ WhisperTamas/
   ├─ WhisperTamas.exe
   ├─ config.toml
   ├─ install_startup.ps1
   ├─ uninstall_startup.ps1
   └─ _internal/
```

## 実行

```powershell
dist\WhisperTamas\WhisperTamas.exe
```

## 配布時の考え方

`dist\WhisperTamas\` はビルド直後の作業ディレクトリです。公開時はそのまま `dist` フォルダを案内するのではなく、次の単位で責務を切り分けると分かりやすくなります。

- 利用者には `README.md` を読めば導入と設定が分かる状態にする
- 公開担当は `dist\WhisperTamas\` の中身を確認してから zip 化やリリース登録を行う
- リリースノートでは `dist` という内部用語より `WhisperTamas.zip` のような配布物名を前面に出す

配布前の最低確認:

- `WhisperTamas.exe` が起動する
- `config.toml` を編集すると挙動が変わる
- `startup.log` と `fault.log` が出力される
- `install_startup.ps1` / `uninstall_startup.ps1` が同梱されている

## スタートアップ登録

配布成果物には以下のスクリプトが含まれます。

- `install_startup.ps1`
- `uninstall_startup.ps1`

通常はトレイメニューから次の操作を使う想定です。

- `Register Startup`
- `Unregister Startup`

## トラブルシューティング

### ビルド時に `Access is denied` が出る

旧バージョンの exe や実行中のプロセスがファイルをロックしている可能性があります。

- 実行中の `WhisperTamas.exe` を終了する
- 古い `dist\whisper-tamas-ui\` を使っていないか確認する
- 必要なら Windows を再起動してから再ビルドする

### トレイメニューの変更が反映されない

古い成果物ではなく、必ず新しい exe を起動してください。

```powershell
dist\WhisperTamas\WhisperTamas.exe
```

### `config.toml` の変更が反映されない

`config.toml` は exe と同じフォルダに置いてください。  
`_internal` の中には置かないでください。

## 補足

- GUI アプリとしてビルドされるため、コンソールは表示されません
- 実行時ログは `startup.log` と `fault.log` に出力されます
- `text_rules` でフィラー語や見出し判定を調整できます
