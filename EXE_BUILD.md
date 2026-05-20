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
