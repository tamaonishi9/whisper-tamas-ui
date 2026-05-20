import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
from faster_whisper import WhisperModel
import tempfile
import time
import os
import pyperclip

# ======================
# 設定
# ======================
DURATION = 5  # 録音秒数
SAMPLE_RATE = 16000
MODEL_SIZE = "small"
DEVICE = "cpu"  # "cuda" に変えるとGPU
COMPUTE_TYPE = "int8"


def main():
    wav_path = None

    try:
        # ======================
        # モデルロード
        # ======================
        print("モデルロード中...")
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        print("モデルロード完了")

        # ======================
        # 録音
        # ======================
        print(f"{DURATION}秒録音開始...")
        audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
        sd.wait()
        print("録音完了")

        # float32 → int16 に変換
        audio = (audio * 32767).astype(np.int16)

        # ======================
        # 一時wav保存
        # ======================
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
            write(wav_path, SAMPLE_RATE, audio)

        # ======================
        # 推論
        # ======================
        print("文字起こし中...")
        start = time.time()

        segments, info = model.transcribe(
            wav_path,
            language="ja",
        )

        text = "".join([seg.text for seg in segments])

        end = time.time()

        # ======================
        # 出力
        # ======================
        pyperclip.copy(text)
        print("クリップボードにコピーしました")

    except Exception as e:
        print(f"エラー: {e}")

    finally:
        if wav_path and os.path.exists(wav_path):
            os.unlink(wav_path)


if __name__ == "__main__":
    main()
