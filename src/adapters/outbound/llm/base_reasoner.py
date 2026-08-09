"""Общая часть LLMReasonerPort для всех провайдеров: построение промпта,
оценка стоимости. Конкретный сетевой вызов (call) реализуют подклассы."""
from __future__ import annotations

from domain.models import LLMUsage
from domain.ports import LLMReasonerPort

from .prompt_builder import build_scenario_bundle_prompt
from .provider_detection import pricing_for


class BaseLLMReasoner(LLMReasonerPort):
    def __init__(self, model: str):
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def pricing_per_million(self) -> tuple[float, float] | None:
        return pricing_for(self._model)

    def build_prompt(
        self,
        scenario_id: str,
        covenant_clauses: dict[str, str],
        supporting_texts: list[tuple[str, str]],
        ledger_rows: list[dict],
    ) -> str:
        return build_scenario_bundle_prompt(scenario_id, covenant_clauses, supporting_texts, ledger_rows)

    def estimate_cost_usd(self, usage: LLMUsage) -> float | None:
        price_in, price_out = pricing_for(self._model)
        return usage.input_tokens * price_in / 1e6 + usage.output_tokens * price_out / 1e6
