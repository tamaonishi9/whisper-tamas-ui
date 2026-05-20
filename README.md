# ローカルで動く高速音声入力ツール（faster-whisperベース）

`faster-whisper` を使った Windows 向けのローカル音声入力ツールです。  
ホットキーで録音を開始し、文字起こし結果をクリップボードへコピーします。

## 最短導入手順

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

起動後はトレイが常駐します。まず `alt+q` か `alt+w` を押して録音できることを確認してください。

## 主な機能

- Global hotkey で録音開始
- `Push2Talk` / `Toggle` の 2 つの入力モード
- `Markdown` / `Plain Text` の 2 つの出力モード
- システムトレイからの有効化 / 無効化
- システムトレイからのスタートアップ登録 / 解除
- `config.toml` でホットキーやテキストルールを調整可能

## 必要環境

- Windows
- Python 3.11 以上
- 動作するマイク入力デバイス

## セットアップ

最短導入手順と同じです。初回はマイク入力が正しく取れるか、通常の `python main.py` 実行で確認するのがおすすめです。

## 使い方

デフォルト設定では以下のホットキーを使用します。

- `alt+q`: Markdown mode で録音
- `alt+w`: Plain Text mode で録音
- `exit = ""`: 終了ホットキーは無効

入力モードはトレイメニューから切り替えます。

- `Push2Talk`: ホットキーを押している間だけ録音
- `Toggle`: 1 回押して録音開始、もう 1 回押して録音終了

## 設定

設定は `config.toml` で変更できます。  
アプリ側の UI やログは英語ベースですが、普段使うテキスト整形ルールは日本語で設定できます。

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
cpu_threads = 4
num_workers = 1

[audio]
sample_rate = 16000
channels = 1
dtype = "float32"
min_record_seconds = 0.2

[output]
markdown_newlines = 1

[text_rules]
filler_phrases = ["えーと、", "えーと", "えっと、", "えっと", "あの、", "あの"]
markdown_title_patterns = ["タイトル", "title"]
markdown_heading_patterns = ["見出し", "heading"]

[tray]
enabled = true
tooltip = "whisper-tamas-ui"
```

### 設定項目一覧

| 項目                       | 説明                                | 目安                                   |
| -------------------------- | ----------------------------------- | -------------------------------------- |
| `hotkey.markdown`          | Markdown モード録音開始ホットキー   | 例: `alt+q`                            |
| `hotkey.plain_text`        | Plain Text モード録音開始ホットキー | 例: `alt+w`                            |
| `hotkey.exit`              | 終了ホットキー。空文字なら無効      | 通常は `""`                            |
| `whisper.model_size`       | 読み込む Whisper モデルサイズ       | 精度重視なら大きめ、軽さ重視なら小さめ |
| `whisper.language`         | 文字起こし言語                      | 日本語なら `ja`                        |
| `whisper.device`           | 推論デバイス                        | CPU は `cpu`、GPU は `cuda`            |
| `whisper.compute_type`     | 推論時の計算精度                    | CPU は `int8` が扱いやすい             |
| `whisper.cpu_threads`      | CPU 推論に使うスレッド数            | CPU 使用率を調整したいときに指定       |
| `whisper.num_workers`      | WhisperModel の worker 数           | CPU ではまず `1` から確認がおすすめ    |
| `audio.sample_rate`        | 録音サンプルレート                  | 通常は `16000`                         |
| `audio.channels`           | 録音チャンネル数                    | 通常は `1`                             |
| `audio.dtype`              | 音声バッファ型                      | 通常は `float32`                       |
| `audio.min_record_seconds` | この秒数未満の録音を破棄            | 誤爆防止なら `0.2` 前後                |
| `output.markdown_newlines` | Markdown 結果の末尾改行数           | 貼り付け先に応じて調整                 |
| `tray.enabled`             | 起動時の音声入力有効状態            | 一時停止したいなら `false`             |
| `tray.tooltip`             | トレイのツールチップ表示名          | 配布名に合わせて調整                   |

### `text_rules`

- `filler_phrases`: 先頭に来たら削除するフィラー語
- `markdown_title_patterns`: `# ...` に変換する接頭辞
- `markdown_heading_patterns`: `## ...` に変換する接頭辞

## ファイル構成

- `main.py`: 起動処理とアプリ組み立て
- `app_controller.py`: メインループと録音フロー
- `recorder.py`: 録音処理
- `audio_feedback.py`: 効果音
- `text_rules.py`: フィラー除去と Markdown 整形
- `tray.py`: システムトレイ UI
- `startup.py`: スタートアップ登録 / 解除支援
- `build.ps1`: EXE ビルドスクリプト
- `EXE_BUILD.md`: EXE 化手順

## 配布とビルド

`README.md` は利用者向けの使い方を扱います。  
EXE の作成方法や `dist\` の扱いは [EXE_BUILD.md](EXE_BUILD.md) に分けています。

## ライセンス

MIT License
