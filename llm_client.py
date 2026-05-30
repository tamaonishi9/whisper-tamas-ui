import json
import urllib.error
import urllib.request

from app_logging import get_logger


logger = get_logger(__name__)


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
