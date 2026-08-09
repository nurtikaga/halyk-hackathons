"""Адаптер LLMReasonerPort поверх Anthropic API."""
from __future__ import annotations
import json

from domain.models import LLMUsage

from .base_reasoner import BaseLLMReasoner
from .prompt_builder import SYSTEM_PROMPT, extract_json


class AnthropicReasoner(BaseLLMReasoner):
    def call(self, prompt: str) -> tuple[dict, LLMUsage]:
        raw_text, usage, stop_reason = self._call_anthropic(prompt)

        if stop_reason == "max_tokens":
            raise RuntimeError(
                f"Ответ обрезан по лимиту max_tokens (finish_reason=max_tokens), "
                f"получено {len(raw_text)} символов, потрачено {usage.output_tokens} "
                f"выходных токенов. Увеличьте max_tokens в reason.py или сократите SYSTEM_PROMPT."
            )

        try:
            return extract_json(raw_text), usage
        except (ValueError, json.JSONDecodeError) as e:
            preview = raw_text[:500].replace("\n", " ")
            raise RuntimeError(f"Не удалось распарсить JSON ({e}). Начало ответа: {preview!r}") from e

    def _call_anthropic(self, user_prompt: str) -> tuple[str, LLMUsage, str]:
        """Возвращает (raw_text, usage, stop_reason)."""
        import anthropic  # локальный импорт - чтобы не требовать пакет, если используется только OpenRouter

        client = anthropic.Anthropic()  # берёт ANTHROPIC_API_KEY из окружения
        resp = client.messages.create(
            model=self._model,
            # 2000 токенов регулярно не хватало: с reasoning на 3 ковенанта ответ
            # обрезался посередине JSON-строки ("Unterminated string...").
            max_tokens=30000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        usage = LLMUsage(input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens)
        raw_text = "".join(block.text for block in resp.content if block.type == "text")
        return raw_text, usage, resp.stop_reason
