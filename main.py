import ctypes
import os
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace

from app_logging import get_logger, setup_logging
from app_controller import AppController
from config import load_config
from datas import AppState
from recorder import PushToTalkRecorder
from llm_client import LlmClient, launch_llm_server
from text_rules import TextRules
from tray import TrayController


logger = get_logger(__name__)


# faster_whisper が内部で av をimportするため、av未インストール環境向けにスタブを注入
def install_faster_whisper_av_stub() -> None:
    if "av" in sys.modules:
        return

    av_stub = ModuleType("av")

    class InvalidDataError(Exception):
        pass

    av_stub.error = SimpleNamespace(InvalidDataError=InvalidDataError)
    sys.modules["av"] = av_stub


# OpenMPライブラリ重複ロードによるエラーを回避
def configure_ctranslate2_runtime() -> None:
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


# 凍結実行ファイルとスクリプト起動の両方に対応したベースディレクトリを返す
def get_app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# PyInstaller凍結時のみ、ctranslate2等のDLLをWindowsのDLL検索パスに追加してプリロード
def configure_frozen_dll_directories() -> None:
    if not getattr(sys, "frozen", False):
        return

    base_dir = get_app_base_dir()
    internal_dir = base_dir / "_internal"
    # CUDA系DLL（cublas/cudnn/nvrtc）はcuda_libsにまとめて配置（GPUビルド時のみ存在）
    cuda_dir = internal_dir / "cuda_libs"
    dll_dirs = [
        internal_dir / "ctranslate2",
        internal_dir / "numpy.libs",
        internal_dir / "onnxruntime" / "capi",
        cuda_dir,
    ]

    for dll_dir in dll_dirs:
        if dll_dir.is_dir():
            os.add_dll_directory(str(dll_dir))
            logger.info("Added DLL directory: %s", dll_dir)

    # CPU実行に必須のDLLを先にプリロード
    preload_dlls = [
        internal_dir / "ctranslate2" / "libiomp5md.dll",
    ]

    # GPU(CUDA)DLLを依存順にプリロードする
    # ctranslate2同梱のcudnn64_8.dllはcudnn_ops/cnn/adv系へ依存するが
    # それらが自動解決されずクラッシュするため、依存側を先に明示ロードする
    cuda_preload_names = [
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "nvrtc64_120_0.dll",
        "cudnn_ops_infer64_8.dll",
        "cudnn_ops_train64_8.dll",
        "cudnn_cnn_infer64_8.dll",
        "cudnn_cnn_train64_8.dll",
        "cudnn_adv_infer64_8.dll",
        "cudnn_adv_train64_8.dll",
        "cudnn64_8.dll",
    ]
    preload_dlls += [cuda_dir / name for name in cuda_preload_names]

    # ctranslate2本体は全依存DLLをロードした後に読み込む
    preload_dlls.append(internal_dir / "ctranslate2" / "ctranslate2.dll")

    for dll_path in preload_dlls:
        if dll_path.is_file():
            ctypes.WinDLL(str(dll_path))
            logger.info("Preloaded DLL: %s", dll_path.name)


# 空文字・"none"文字列をNoneに統一し、未設定ホットキーを表現
def normalize_optional_hotkey(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized or normalized.lower() == "none":
        return None
    return normalized


# WhisperModelを生成して返す。importまたは生成失敗時はNoneを返す
def create_model(
    model_size: str,
    device: str,
    compute_type: str,
    cpu_threads: int | None,
    num_workers: int,
):
    logger.info("About to import faster_whisper")
    try:
        configure_frozen_dll_directories()
        install_faster_whisper_av_stub()
        logger.info("Installed av stub for faster_whisper")
        from faster_whisper import WhisperModel
    except Exception as error:
        logger.exception("faster_whisper import failed: %s", error)
        return None

    logger.info("faster_whisper import completed")
    logger.info("About to create WhisperModel")

    try:
        configure_ctranslate2_runtime()
        logger.info(
            "CTranslate2 runtime configured: cpu_threads=%s, num_workers=%s, OMP_NUM_THREADS=%s",
            cpu_threads,
            num_workers,
            os.environ.get("OMP_NUM_THREADS"),
        )

        model_kwargs = {
            "device": device,
            "compute_type": compute_type,
            "num_workers": num_workers,
        }
        if cpu_threads is not None:
            model_kwargs["cpu_threads"] = cpu_threads

        model = WhisperModel(model_size, **model_kwargs)
    except Exception as error:
        logger.exception("WhisperModel creation failed: %s", error)
        return None

    logger.info("WhisperModel creation completed")
    return model


# 設定読み込み・モデル初期化・各コンポーネント起動
def main() -> None:
    setup_logging(get_app_base_dir())
    config = load_config()
    logger.info("Application start")

    # ホットキー設定の正規化
    hotkey_markdown = normalize_optional_hotkey(config["hotkey"]["markdown"])
    hotkey_plain_text = normalize_optional_hotkey(config["hotkey"]["plain_text"])
    exit_hotkey = normalize_optional_hotkey(config["hotkey"]["exit"])

    # 音声設定
    sample_rate = config["audio"]["sample_rate"]
    channels = config["audio"]["channels"]
    dtype = config["audio"]["dtype"]
    min_record_seconds = config["audio"]["min_record_seconds"]

    # Whisper設定
    model_size = config["whisper"]["model_size"]
    language = config["whisper"]["language"]
    device = config["whisper"]["device"]
    compute_type = config["whisper"]["compute_type"]
    cpu_threads = config["whisper"].get("cpu_threads")
    num_workers = config["whisper"]["num_workers"]

    # 出力・トレイ設定
    markdown_newlines = config["output"]["markdown_newlines"]
    tray_enabled = config["tray"]["enabled"]
    tray_tooltip = config["tray"]["tooltip"]

    # LLM設定読み込みとクライアント初期化
    llm_config = config.get("llm", {})
    llm_enabled = llm_config.get("enabled", False)
    llm_client = None

    if llm_enabled:
        # 設定があれば録音前にローカルLLMサーバーを起動しておく
        launch_command = llm_config.get("launch_command", "")
        if launch_command:
            launch_llm_server(launch_command, cwd=str(get_app_base_dir()))

        llm_model = llm_config.get("model", "")
        if not llm_model:
            # model未設定時はLLMをスキップしてフォールバック動作を維持
            logger.warning("LLM is enabled but model is not configured. LLM will be skipped.")
        else:
            llm_client = LlmClient(
                base_url=llm_config.get("base_url", "http://127.0.0.1:1234/v1"),
                api_key=llm_config.get("api_key", ""),
                model=llm_model,
                timeout_seconds=llm_config.get("timeout_seconds", 10.0),
                prompt=llm_config.get("prompt", ""),
                glossary=llm_config.get("glossary", []),
            )
            logger.info("LLM client initialized: model=%s", llm_model)

    logger.info(
        "Config whisper settings: model_size=%s, language=%s, device=%s, compute_type=%s, cpu_threads=%s, num_workers=%s",
        model_size,
        language,
        device,
        compute_type,
        cpu_threads,
        num_workers,
    )

    # ホットキー未設定チェック
    if hotkey_markdown is None and hotkey_plain_text is None:
        logger.error(
            "Configuration error: either the Markdown or Plain Text hotkey must be configured"
        )
        return

    # モデル読み込み
    logger.info("Loading model...")
    model = create_model(model_size, device, compute_type, cpu_threads, num_workers)
    if model is None:
        return
    logger.info("Model loaded")

    # 各コンポーネント初期化
    text_rules = TextRules.from_config(config)
    recorder = PushToTalkRecorder(
        sample_rate=sample_rate,
        channels=channels,
        dtype=dtype,
    )
    app_state = AppState(enabled=tray_enabled)
    tray = TrayController(app_state, tooltip=tray_tooltip)

    # PILのPNGエンコーダをメインスレッドで温めておく
    # （pystrayスレッドでの初回遅延ロードによるaccess violation回避）
    tray.prewarm_icon_encoder()

    # トレイを別スレッドで起動
    tray_thread = threading.Thread(target=tray.start, daemon=True)
    tray_thread.start()

    # メインコントローラーを起動（ブロッキング）
    controller = AppController(
        recorder=recorder,
        model=model,
        app_state=app_state,
        tray=tray,
        text_rules=text_rules,
        hotkey_markdown=hotkey_markdown,
        hotkey_plain_text=hotkey_plain_text,
        exit_hotkey=exit_hotkey,
        language=language,
        min_record_seconds=min_record_seconds,
        markdown_newlines=markdown_newlines,
        llm_client=llm_client,
    )
    controller.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        setup_logging(get_app_base_dir())
        logger.exception("Unhandled exception: %s", error)
        raise
