import faulthandler
import logging
import sys
from pathlib import Path


LOGGER_NAME = "whisper_tamas"


# 指定した名前の子ロガーを返す。Noneならルートロガーを返す
def get_logger(name: str | None = None) -> logging.Logger:
    base_logger = logging.getLogger(LOGGER_NAME)
    if name is None:
        return base_logger
    return base_logger.getChild(name)


# コンソール・ファイル・faulthandlerの3系統でログを初期化する
def setup_logging(base_dir: Path) -> tuple[Path, Path]:
    logger = get_logger()
    diagnostic_path = base_dir / "startup.log"
    fault_path = base_dir / "fault.log"

    if logger.handlers:
        return diagnostic_path, fault_path

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(diagnostic_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # fault.logはプロセス終了まで開放しない（faulthandler要件）
    fault_stream = open(fault_path, "a", encoding="utf-8")
    faulthandler.enable(file=fault_stream, all_threads=True)

    logger.info("Diagnostics enabled: %s", diagnostic_path)
    logger.info("Fault handler enabled: %s", fault_path)
    logger.info("Python executable: %s", sys.executable)
    logger.info("Frozen: %s", getattr(sys, "frozen", False))
    return diagnostic_path, fault_path
