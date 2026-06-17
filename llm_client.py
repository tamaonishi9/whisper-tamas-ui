import ctypes
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

from app_logging import get_logger


logger = get_logger(__name__)


# PyInstallerが変更したDLL検索ディレクトリを外部プロセス起動中だけ解除する
@contextmanager
def _clean_windows_dll_search_path():
    if os.name != "nt":
        yield
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_dll_directory = kernel32.SetDllDirectoryW
    set_dll_directory.argtypes = [ctypes.c_wchar_p]
    set_dll_directory.restype = ctypes.c_bool

    restore_path = getattr(sys, "_MEIPASS", None)

    # 外部exeがWhisperTamas同梱DLLを誤読込しないよう、子プロセス生成前に既定検索へ戻す
    set_dll_directory(None)
    try:
        yield
    finally:
        # frozenアプリ本体の後続処理を壊さないよう、PyInstallerのDLL検索先を復元する
        if restore_path:
            set_dll_directory(str(restore_path))


# PyInstaller実行プロセスのDLL/PATH環境を子プロセスへ渡さないための最小環境を作る
def _build_clean_launch_env() -> dict[str, str]:
    env = os.environ.copy()
    app_dir = str(Path(sys.executable).resolve().parent).lower()

    # PyInstallerやPython実行環境の変数は、外部exeのDLL探索を誤らせるため除外する
    for key in list(env):
        upper_key = key.upper()
        if upper_key.startswith("PYINSTALLER") or upper_key in {"PYTHONHOME", "PYTHONPATH"}:
            env.pop(key, None)

    # PATHからアプリ配下を外し、llama-serverが自分の配置先DLLを優先して読む状態に戻す
    path_parts = []
    for path_part in env.get("PATH", "").split(os.pathsep):
        normalized = path_part.strip().lower()
        if normalized and not normalized.startswith(app_dir):
            path_parts.append(path_part)

    system_paths = [
        r"C:\Windows\System32",
        r"C:\Windows",
        r"C:\Windows\System32\Wbem",
        r"C:\Windows\System32\WindowsPowerShell\v1.0",
    ]
    env["PATH"] = os.pathsep.join(system_paths + path_parts)
    return env


# Windowsコマンドの先頭実行ファイルと残り引数を分け、bat/cmdの相対パス解決に使う
def _split_launch_command(command: str) -> tuple[str, str]:
    stripped = command.strip()
    if not stripped:
        return "", ""

    # 先頭が引用符の場合、空白を含むパスを1トークンとして扱う
    if stripped[0] == '"':
        closing_quote = stripped.find('"', 1)
        if closing_quote == -1:
            return stripped.strip('"'), ""
        executable = stripped[1:closing_quote]
        arguments = stripped[closing_quote + 1 :].strip()
        return executable, arguments

    # 未引用の場合、最初の空白までを実行ファイルとして扱う
    parts = stripped.split(maxsplit=1)
    executable = parts[0]
    arguments = parts[1] if len(parts) > 1 else ""
    return executable, arguments


# bat/cmdはcmd.exe経由で窓を出さずに起動し、出力はログへ残す
def _launch_batch_file(
    command: str, cwd: str | None = None
) -> tuple[bool, subprocess.Popen | None]:
    executable, arguments = _split_launch_command(command)
    if not executable:
        return False, None

    batch_path = Path(executable)
    if batch_path.suffix.lower() not in {".bat", ".cmd"}:
        return False, None

    # 相対パスはアプリ配置ディレクトリ基準で解決し、EXE起動時の作業ディレクトリ差を吸収する
    if not batch_path.is_absolute():
        batch_path = Path(cwd or os.getcwd()) / batch_path
    batch_path = batch_path.resolve()

    if not batch_path.is_file():
        logger.warning("LLM launch batch not found: %s", batch_path)
        return True, None

    # call経由にしてbatの終了コードをcmd.exeへ伝える
    # cwdをbat配置先へ固定し、cmd.exeのパス引用符解釈による%~dp0破損を避ける
    batch_command = f"call {batch_path.name}"
    if arguments:
        batch_command = f"{batch_command} {arguments}"

    launch_log_path = batch_path.parent / "llm-server-launch.log"

    with _clean_windows_dll_search_path():
        with open(launch_log_path, "a", encoding="utf-8", errors="replace") as log_file:
            process = subprocess.Popen(
                ["cmd.exe", "/d", "/c", batch_command],
                cwd=str(batch_path.parent),
                env=_build_clean_launch_env(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    logger.info(
        "LLM launch batch started: %s (cwd=%s, log=%s)",
        batch_path,
        batch_path.parent,
        launch_log_path,
    )
    return True, process


# 設定されたコマンドでローカルLLMサーバーをバックグラウンド起動する
# 応答は録音完了まで不要なのでfire-and-forgetで待たない
# bat/cmdは窓なしで起動し、サーバー出力と失敗理由をログに残す
def launch_llm_server(command: str, cwd: str | None = None) -> subprocess.Popen | None:
    try:
        # bat/cmdはShellExecuteではなくcmd.exe /cで起動し、コンソール窓を出さない
        handled, batch_process = _launch_batch_file(command, cwd=cwd)
        if handled:
            return batch_process

        # bat/cmd以外の任意コマンドは既存互換のshell実行を維持する
        with _clean_windows_dll_search_path():
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                env=_build_clean_launch_env(),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        logger.info("LLM server launched: %s (cwd=%s)", command, cwd)
        return process
    except Exception as e:
        logger.warning("LLM server launch failed: %s", e)
        return None


# このアプリが起動したLLMサーバープロセスツリーだけを終了する
def stop_llm_server(process: subprocess.Popen | None) -> None:
    if process is None:
        return

    if process.poll() is not None:
        logger.info("LLM server process already exited: pid=%s", process.pid)
        return

    # Windowsではbat/cmd配下のllama-serverまで含めて、このPopen配下だけを終了する
    if os.name == "nt":
        logger.info("Stopping LLM server process tree: pid=%s", process.pid)
        completed = subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_build_clean_launch_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            logger.warning(
                "LLM server process tree stop failed: pid=%s output=%s",
                process.pid,
                completed.stdout.strip(),
            )
        return

    # Windows以外では親プロセスだけを穏当に終了し、残る場合のみ強制終了する
    logger.info("Stopping LLM server process: pid=%s", process.pid)
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()


class LlmClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        prompt: str,
        glossary: list[str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.prompt = prompt
        self.glossary = glossary or []

    # glossary設定済みの場合、プロンプト末尾に用語集セクションを付加してsystem contentを組み立てる
    def _build_system_content(self) -> str:
        if not self.glossary:
            return self.prompt
        terms = "\n".join(f"- {term}" for term in self.glossary)
        return (
            f"{self.prompt}\n\n## Glossary\n\n"
            f"The following terms may have been incorrectly transcribed by speech recognition.\n"
            f"If a similar-sounding or partially-translated form appears in the input, "
            f"correct it to the canonical form listed below:\n{terms}"
        )

    # OpenAI互換Chat Completions APIを呼び出し、後処理済みテキストを返す。失敗時はNoneを返す
    def process(self, text: str) -> str | None:
        url = f"{self.base_url}/chat/completions"

        # systemにプロンプト設定値（用語集含む）、userに文字起こし本文を分離して渡す
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._build_system_content()},
                {"role": "user", "content": text},
            ],
        }

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        # HTTP接続・応答取得（urllib単一タイムアウト制約を許容）
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            logger.warning("LLM API HTTP error: %s %s. Falling back.", e.code, e.reason)
            return None
        except urllib.error.URLError as e:
            logger.warning("LLM API connection failed: %s. Falling back.", e.reason)
            return None
        except TimeoutError:
            logger.warning("LLM API timed out. Falling back.")
            return None
        except Exception as e:
            logger.warning("LLM API unexpected error: %s. Falling back.", e)
            return None

        # 応答JSONからテキスト内容を取り出す
        try:
            data = json.loads(response_body)
            result = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as e:
            logger.warning("LLM API response parse error: %s. Falling back.", e)
            return None

        if not result or not result.strip():
            logger.warning("LLM API returned empty content. Falling back.")
            return None

        return result.strip()
