# whisper-tamas-ui - EXEビルド手順

---

## EXE化手順

`whisper-tamas-ui` を **exe形式で実行できるようにする手順**です。
Python環境なしでの起動や、スタートアップ登録・常駐運用を目的としています。

---

### 概要

このプロジェクトは通常、以下で起動します。

```bash
python main.py
```

本ガイドではこれを **`.exe` に変換**し、以下を実現します。

- Python不要で起動
- トレイ常駐アプリとして運用
- スタートアップ登録が可能
- アプリ名で表示（Python表示回避）

---

### 前提環境

- Windows
- Python 3.11 以上
- 仮想環境（推奨）

---

### セットアップ

#### 1. 仮想環境の作成（未作成の場合）

```bash
python -m venv .venv
```

#### 2. 仮想環境の有効化

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

cmd:

```cmd
.venv\Scripts\activate.bat
```

---

#### 3. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

追加で PyInstaller をインストールします。

```bash
pip install pyinstaller
```

このリポジトリには EXE ビルド用の `build.ps1` も含まれています。
以降はこのスクリプトを使うと、`config.toml` を exe の横へコピーするところまでまとめて実行できます。

---

### 動作確認（重要）

exe化の前に、必ず通常実行で動作確認してください。

```bash
python main.py
```

確認項目:

- トレイ常駐する
- `alt+q` → Markdown モード録音
- `alt+w` → Plain Text モード録音
- `exit = ""` のままなら終了ホットキーは無効
- `config.toml` が反映される
- 音声認識が動く

---

### EXEビルド

#### 推奨手順

```powershell
.\build.ps1
```

`build.ps1` は内部で次のコマンドを実行します。

```powershell
pyinstaller main.py --name whisper-tamas-ui --onedir
Copy-Item config.toml dist\whisper-tamas-ui\config.toml -Force
```

この手順により、`config.toml` も自動で `dist\whisper-tamas-ui\` に配置されます。

---

### ビルド結果

```text
dist/
└─ whisper-tamas-ui/
   ├─ whisper-tamas-ui.exe
   ├─ ...
```

---

### 設定ファイル配置

`build.ps1` を使う場合、`config.toml` は自動で exe と同じフォルダに配置されます。

現在の実装では、`config.toml` は実行ファイルの配置ディレクトリを基準に読み込まれます。
そのため、ショートカットやスタートアップから起動しても、exe の横に置いた `config.toml` が参照されます。

```text
dist/
└─ whisper-tamas-ui/
   ├─ whisper-tamas-ui.exe
   ├─ config.toml
```

---

### 実行方法

```bash
dist\whisper-tamas-ui\whisper-tamas-ui.exe
```

---

### 動作確認

#### 起動確認

- exeが起動する
- エラーで即終了しない
- モデルロードが成功する

#### 機能確認

- トレイに常駐する
- ホットキーが動作する
- 録音→文字起こし→クリップボードが動く

---

### ビルドオプション（後で調整）

#### コンソール非表示

安定後に以下を使用:

```powershell
pyinstaller main.py --name whisper-tamas-ui --onedir --noconsole
Copy-Item config.toml dist\whisper-tamas-ui\config.toml -Force
```

---

#### onefile化（上級者向け）

```powershell
pyinstaller main.py --name whisper-tamas-ui --onefile
Copy-Item config.toml dist\config.toml -Force
```

※ faster-whisper の都合で問題が出る場合あり
まずは `onedir` を推奨

---

### トラブルシューティング

#### 起動しない

- 仮想環境で `python main.py` が動くか確認
- 依存が不足していないか確認
- exe と同じフォルダに出力される `startup.log` と `fault.log` を確認

---

#### config.toml が読まれない

- `build.ps1` 実行後に `dist\whisper-tamas-ui\config.toml` が生成されているか確認
- `whisper-tamas-ui.exe` と同じディレクトリにあるか確認
- `_internal` の中ではなく、exe の横に置かれているか確認

---

#### モデルロード失敗

- 初回ダウンロードが必要な場合あり
- ネットワーク状態を確認

---

#### トレイが出ない

- バックグラウンドで落ちていないか確認
- consoleありビルドでログを見る

---

### 次のステップ

- スタートアップ登録（Phase6-2）
- UX改善（Phase6-3）
- 誤認識辞書の導入
- GPU対応検証

---

### ライセンス

MIT License

---

## 動作確認済み環境

2026-04-04 時点で、以下の構成で `build.ps1` による EXE ビルドと起動を確認しました。

- OS: Windows 11
- Python: 3.12.10
- PyInstaller: 6.19.0
- ビルド出力先: `dist\whisper-tamas-ui`
- 起動確認: `startup.log` で `WhisperModel creation completed` まで到達
- fault.log: 空ファイルを確認

依存バージョン:

- `faster-whisper==1.0.3`
- `ctranslate2==4.4.0`
- `av==12.3.0`
- `requests==2.32.3`
- `setuptools==80.9.0`

この環境では、以下の調整を入れた状態で動作確認しています。

- `whisper-tamas-ui.spec` は `main.py` をエントリーポイントに使用
- `upx=False`
- `build.ps1` は `.venv\Scripts\python.exe -m PyInstaller` を使用
- frozen 実行時に `_internal\ctranslate2` などの DLL ディレクトリを追加
- `faster_whisper` import 時は `av` スタブを使用
- `WhisperModel` 初期化時は `num_workers=1` を指定

補足:

- 上記設定により EXE 起動は安定しましたが、文字起こし速度は以前より遅く感じる可能性があります。
- 必要に応じて `num_workers` は見直し可能です。
