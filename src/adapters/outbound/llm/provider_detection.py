"""
Определение, каким провайдером LLM пользоваться, и по какой цене.

Поддерживает ТРИ провайдера через один и тот же порт (LLMReasonerPort):
  - Anthropic API (claude-fable-5, claude-opus-4-8, claude-sonnet-5, ...)
  - OpenRouter (openrouter.ai)
  - TokenRouter (tokenrouter.com) или ЛЮБОЙ ДРУГОЙ OpenAI-совместимый шлюз

Выбор провайдера:
  1) Если задан HALYK_API_BASE_URL - используется ОН (универсальный режим,
     подходит для TokenRouter и любого другого OpenAI-совместимого шлюза).
     Ключ берётся из HALYK_API_KEY.
  2) Иначе если задан TOKENROUTER_API_KEY - автоматически используется
     TokenRouter (https://api.tokenrouter.com/v1).
  3) Иначе если задан OPENROUTER_API_KEY И в имени модели есть "/" -
     используется OpenRouter (https://openrouter.ai/api/v1).
  4) Иначе - Anthropic API (ANTHROPIC_API_KEY).
Переопределить явно можно через HALYK_PROVIDER=anthropic|openrouter|tokenrouter|custom.
"""
from __future__ import annotations
import os
from dataclasses import dataclass

# Известные OpenAI-совместимые шлюзы "из коробки" - для них не нужно вручную
# указывать HALYK_API_BASE_URL, достаточно положить в .env их собственный ключ.
KNOWN_GATEWAYS = {
    "tokenrouter": {"base_url": "https://api.tokenrouter.com/v1", "key_env": "TOKENROUTER_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY"},
}

# Цены за 1М токенов, USD. Используются только для оценки расхода на лету -
# не влияют на сам биллинг (тот считает провайдер по факту), но позволяют
# вести бюджет и остановиться ДО того, как деньги кончатся, а не после.
# Кимi K3 через OpenRouter - $3 input / $15 output по состоянию на момент
# написания; провайдеры/цены на OpenRouter могут меняться - если видите
# в логе оценку, сильно отличающуюся от реального списания в личном
# кабинете OpenRouter, поправьте цифры здесь.
PRICING_PER_MILLION = {
    "claude-fable-5": (10, 50),
    "claude-mythos-5": (10, 50),
    "claude-opus-4-8": (5, 25),
    "claude-sonnet-5": (2, 10),
    "claude-haiku-4-5-20251001": (0.8, 4),
}

DEFAULT_MODEL = os.environ.get("HALYK_AGENT_MODEL", "moonshotai/Kimi-K3")


@dataclass(frozen=True)
class ProviderConfig:
    provider: str  # "anthropic" | "custom" | "tokenrouter" | "openrouter"
    base_url: str | None
    api_key: str | None
    model: str


def detect_provider(model: str = DEFAULT_MODEL) -> ProviderConfig:
    """Возвращает конфигурацию провайдера. base_url/api_key = None у anthropic."""
    override = os.environ.get("HALYK_PROVIDER", "").strip().lower()

    # 1) Явный универсальный режим - свой/любой OpenAI-совместимый шлюз.
    # Для Modal Auto Endpoint API key может не требоваться, поэтому пустой
    # HALYK_API_KEY является допустимым значением.
    custom_base_url = os.environ.get("HALYK_API_BASE_URL", "").strip()
    if custom_base_url or override == "custom":
        return ProviderConfig(
            "custom", custom_base_url, os.environ.get("HALYK_API_KEY", "").strip() or None, model
        )

    # 2) Явное переопределение на известный шлюз
    if override in KNOWN_GATEWAYS:
        g = KNOWN_GATEWAYS[override]
        return ProviderConfig(override, g["base_url"], os.environ.get(g["key_env"]), model)

    if override == "anthropic":
        return ProviderConfig("anthropic", None, None, model)

    # 3) Автоопределение по тому, какой ключ реально задан в окружении
    if os.environ.get("TOKENROUTER_API_KEY"):
        g = KNOWN_GATEWAYS["tokenrouter"]
        return ProviderConfig("tokenrouter", g["base_url"], os.environ.get(g["key_env"]), model)
    if os.environ.get("OPENROUTER_API_KEY") and "/" in model:
        g = KNOWN_GATEWAYS["openrouter"]
        return ProviderConfig("openrouter", g["base_url"], os.environ.get(g["key_env"]), model)

    return ProviderConfig("anthropic", None, None, model)


def pricing_for(model: str) -> tuple[float, float]:
    return PRICING_PER_MILLION.get(model, (10, 50))
