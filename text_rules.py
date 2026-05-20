import re


class TextRules:
    def __init__(
        self,
        filler_phrases: list[str],
        markdown_title_patterns: list[str],
        markdown_heading_patterns: list[str],
    ) -> None:
        self.filler_phrases = [phrase.strip() for phrase in filler_phrases if phrase.strip()]
        self.markdown_title_patterns = self._normalize_patterns(markdown_title_patterns)
        self.markdown_heading_patterns = self._normalize_patterns(markdown_heading_patterns)

    @staticmethod
    def _normalize_patterns(patterns: list[str]) -> list[str]:
        return [pattern.strip() for pattern in patterns if pattern.strip()]

    # 設定dictからTextRulesを生成
    @classmethod
    def from_config(cls, config: dict) -> "TextRules":
        rules = config.get("text_rules", {})
        return cls(
            filler_phrases=list(rules.get("filler_phrases", [])),
            markdown_title_patterns=list(rules.get("markdown_title_patterns", [])),
            markdown_heading_patterns=list(rules.get("markdown_heading_patterns", [])),
        )

    # 空白・改行を正規化してテキストを1行に整形
    def normalize_text(self, text: str) -> str:
        text = text.strip()
        text = text.replace("\n", " ")
        return " ".join(text.split())

    # モードに応じてテキストを整形（markdownのみ特殊処理）
    def format_text_by_mode(self, text: str, mode: str | None) -> str:
        if mode == "markdown":
            return self.format_markdown_text(text)
        return text

    # フィラー除去→タイトル/見出しパターン判定→箇条書きにフォールバック
    def format_markdown_text(self, text: str) -> str:
        text = self.strip_filler(text).strip()
        if not text:
            return ""

        title_pattern = self._build_prefixed_pattern(self.markdown_title_patterns)
        heading_pattern = self._build_prefixed_pattern(self.markdown_heading_patterns)

        patterns = [
            (title_pattern, "# {}"),
            (heading_pattern, "## {}"),
        ]

        for pattern, template in patterns:
            if pattern is None:
                continue

            match = re.match(pattern, text, flags=re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                if content:
                    return template.format(content)

        return f"- {text}"

    # 先頭のフィラー語句を1つ除去
    def strip_filler(self, text: str) -> str:
        text = text.strip()

        for filler in self.filler_phrases:
            if text.startswith(filler):
                return text[len(filler) :].strip()

        return text

    # プレフィックスリストからマッチ用正規表現を構築（例: "タイトル:〇〇"）
    @staticmethod
    def _build_prefixed_pattern(prefixes: list[str]) -> str | None:
        if not prefixes:
            return None

        escaped = "|".join(re.escape(prefix) for prefix in prefixes)
        return rf"^(?:{escaped})\s*[:：]?\s*(.+)$"
