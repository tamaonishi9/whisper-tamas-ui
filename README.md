# whisper-tamas-ui

Whisper を使ったローカル音声入力ツールです。ホットキーを押している間だけ録音し、文字起こし結果をクリップボードへコピーします。

## 使い方

`python main.py` で起動します。

- `alt+q`: Obsidian 用で録音
- `alt+w`: Prompt 用で録音
- `esc`: 終了

## 設定

設定は `config.toml` で変更できます。主な項目は次のとおりです。

- `[hotkey]`: ホットキー設定
- `[whisper]`: モデルサイズ、言語、実行デバイス
- `[audio]`: サンプルレート、チャンネル数、最小録音秒数
- `[output]`: 出力整形の設定。`obsidian_newlines` で末尾の改行数を指定

`config.toml` が存在しない場合や読み込みに失敗した場合は、`config.py` のデフォルト設定を使って起動します。
