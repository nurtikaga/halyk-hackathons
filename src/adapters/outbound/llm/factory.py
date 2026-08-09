"""Composition helper: строит конкретный LLMReasonerPort по конфигурации окружения.
Это единственное место, кроме adapters/inbound/*, где домен "узнаёт" о конкретных
классах адаптеров - то есть композиционный корень для LLM-порта."""
from __future__ import annotations

from domain.ports import LLMReasonerPort

from .anthropic_reasoner import AnthropicReasoner
from .openai_compatible_reasoner import OpenAICompatibleReasoner
from .provider_detection import ProviderConfig, detect_provider


def build_reasoner(model: str | None = None) -> tuple[LLMReasonerPort, ProviderConfig]:
    cfg = detect_provider(model) if model else detect_provider()
    if cfg.provider == "anthropic":
        return AnthropicReasoner(cfg.model), cfg
    return OpenAICompatibleReasoner(cfg.model, cfg.provider, cfg.base_url, cfg.api_key), cfg
