# whisper-tamas-ui

`faster-whisper` を使った Windows 向けのローカル音声入力ツールです。ホットキーで録音を開始し、音声を文字起こししてクリップボードへコピーします。

`Markdown` と `Plain Text` の 2 モードを持っていて、トレイメニューから有効/無効や入力方式を切り替えられます。

## 主な機能

- グローバルホットキーで録音開始
- `Push-to-Talk` と `Toggle` の 2 つの入力モード
- `faster-whisper` によるローカル文字起こし
- 結果を自動でクリップボードへコピー
- Markdown 向けの簡易整形
- システムトレイから状態確認、無効化、終了が可能
- 開始・完了・エラー時のビープ音

## 動作概要

このアプリは `main.py` から起動します。音声入力は `sounddevice` で取得し、`WhisperModel` で文字起こしした結果をモード別に整形して `pyperclip` でクリップボードへコピーします。

トレイアイコンは `tray.py` で管理しており、現在の状態に応じて次を切り替えられます。

- アプリの有効/無効
- 入力モード: `Push2Talk` / `Toggle`
- アプリ終了

## 必要環境

- Windows
- Python 3.11 以上
- マイク入力が利用可能な環境

`winsound` を使っているため、現在の実装は Windows 前提です。

## セットアップ

1. 仮想環境を作成して有効化します。
2. 依存関係をインストールします。
3. 必要に応じて `config.toml` を編集します。
4. `python main.py` で起動します。

例:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## 使い方

デフォルト設定では次のホットキーが使われます。

- `alt+q`: Markdown モードで録音
- `alt+w`: Plain Text モードで録音
- `esc`: 終了

初期状態の入力モードは `Push-to-Talk` です。

- `Push-to-Talk`: ホットキーを押している間だけ録音します
- `Toggle`: ホットキーを 1 回押して録音開始、同じホットキーでもう 1 回押して録音終了します

`Toggle` モードで録音中に別モードのホットキーを押すと、現在の録音を破棄して新しいモードで録音をやり直します。

## 出力ルール

### Markdown モード

Markdown モードでは、文字起こし結果に対して次の整形を行います。

- 先頭のフィラー語を除去します
  - 対象例: `えーと`, `えっと`, `あの` など
- `タイトル: ...` または `title: ...` で始まる場合は `# 見出し` に変換します
- `見出し: ...` または `heading: ...` で始まる場合は `## 見出し` に変換します
- それ以外は `- ` を付けて箇条書きにします
- 末尾に `markdown_newlines` で指定した数の改行を追加します

### Plain Text モード

- 文字起こし結果をそのままクリップボードへコピーします

## 設定

設定は `config.toml` で上書きできます。ファイルが存在しない場合や読み込みに失敗した場合は、`config.py` のデフォルト設定が使われます。

現在のデフォルト設定:

```toml
[hotkey]
markdown = "alt+q"
plain_text = "alt+w"
exit = ""

[whisper]
model_size = "small"
language = "ja"
device = "cpu"
compute_type = "int8"

[audio]
sample_rate = 16000
channels = 1
dtype = "float32"
min_record_seconds = 0.2

[output]
markdown_newlines = 1

[tray]
enabled = true
tooltip = "whisper-tamas-ui"
```

各セクションの意味:

- `[hotkey]`: モード別の録音開始キーと終了キー
- `[whisper]`: モデルサイズ、言語、実行デバイス、計算精度
- `[audio]`: 録音時のサンプルレート、チャンネル数、dtype、最小録音秒数
- `[output]`: Markdown モードの出力改行数
- `[tray]`: トレイ関連の設定値

補足:

- `hotkey.markdown` または `hotkey.plain_text` のどちらか 1 つは必須です
- 空文字列または `"none"` を設定したホットキーは無効になります
- `min_record_seconds` 未満の短い録音は文字起こしせず破棄されます
- `[tray]` セクションの値は現状の実装では参照されていません

## ファイル構成

- `main.py`: 録音、文字起こし、ホットキー監視、出力処理の本体
- `tray.py`: システムトレイ UI
- `config.py`: デフォルト設定と `config.toml` のマージ処理
- `config.toml`: ユーザー設定
- `datas.py`: アプリ状態の共有データ
- `build.ps1`: `config.toml` を含めて EXE をビルドする PowerShell スクリプト
- `EXE_BUILD.md`: EXE 化の手順書

## ライセンス

MIT License
