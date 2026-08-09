"""
Адаптер LLMReasonerPort поверх OpenAI-совместимого Chat Completions API
(OpenRouter, TokenRouter, или любой другой шлюз, включая Modal Auto Endpoint).
"""
from __future__ import annotations
import json
import os
import time

import requests

from domain.models import LLMUsage

from .base_reasoner import BaseLLMReasoner
from .prompt_builder import SYSTEM_PROMPT, extract_json


class OpenAICompatibleReasoner(BaseLLMReasoner):
    def __init__(self, model: str, provider: str, base_url: str, api_key: str | None):
        super().__init__(model)
        self._provider = provider
        self._base_url = base_url
        self._api_key = api_key

    def estimate_cost_usd(self, usage: LLMUsage) -> float | None:
        # Modal Kimi K3 Auto Endpoint тарифицируется по compute-времени, а не по
        # токенам. Поэтому не подставляем сюда цены Shared API K3: это было бы
        # неправильной оценкой стоимости.
        if self._provider == "custom" and "modal.direct" in (self._base_url or ""):
            return None
        return super().estimate_cost_usd(usage)

    def call(self, prompt: str) -> tuple[dict, LLMUsage]:
        raw_text, usage, stop_reason = self._call_openai_compatible(prompt)

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

    def _call_openai_compatible(self, user_prompt: str) -> tuple[str, LLMUsage, str]:
        """
        Для обычных провайдеров (OpenRouter/TokenRouter) используется API key.
        Для Modal custom endpoint API key не требуется.
        """
        if self._provider != "custom" and not self._api_key:
            raise RuntimeError(
                f"Ключ для провайдера {self._provider!r} не найден в окружении/.env "
                f"(base_url={self._base_url!r}). Проверьте HALYK_API_KEY / TOKENROUTER_API_KEY / "
                f"OPENROUTER_API_KEY в зависимости от того, каким шлюзом пользуетесь."
            )

        headers = {
            "Content-Type": "application/json",
        }

        # Modal Kimi K3 сейчас используется без Bearer authentication.
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "max_tokens": 30000,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }

        # Retry ТОЛЬКО на обрывах соединения/таймаутах - типичная картина для
        # Modal при холодном старте контейнера (RemoteDisconnected, если
        # соединение рвётся раньше, чем контейнер поднялся и ответил). Сам
        # запрос (headers/payload/timeout/url) не меняется между попытками.
        max_attempts = int(os.environ.get("HALYK_MAX_RETRIES", "3"))
        backoff_seconds = (10, 30, 60)
        last_error = None
        resp = None
        for attempt in range(max_attempts):
            try:
                resp = requests.post(
                    f"{self._base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=600,
                )
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = e
                if attempt < max_attempts - 1:
                    wait = backoff_seconds[min(attempt, len(backoff_seconds) - 1)]
                    print(f"    ! Обрыв соединения с {self._provider} (попытка {attempt + 1}/{max_attempts}): "
                          f"{e}. Повтор через {wait} сек (возможен холодный старт контейнера) ...")
                    time.sleep(wait)
        if resp is None:
            raise RuntimeError(
                f"Не удалось достучаться до {self._provider} за {max_attempts} попыток. "
                f"Последняя ошибка: {last_error}"
            )

        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"{self._provider} вернул ошибку: {data['error']}")

        choice = data["choices"][0]
        raw_text = choice["message"]["content"] or ""

        stop_reason_raw = choice.get("finish_reason", "")
        stop_reason = (
            "max_tokens"
            if stop_reason_raw in ("length", "max_tokens")
            else stop_reason_raw
        )

        usage_raw = data.get("usage", {})
        usage = LLMUsage(
            input_tokens=usage_raw.get("prompt_tokens", 0),
            output_tokens=usage_raw.get("completion_tokens", 0),
        )

        return raw_text, usage, stop_reason
