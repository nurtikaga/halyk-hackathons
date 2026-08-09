"""Чистое преобразование "сырого" JSON от LLM в доменный объект CovenantAnswer.

Не зависит от того, какой провайдер вернул JSON - только от согласованного
формата ответа (см. LLMReasonerPort / SYSTEM_PROMPT в adapters/outbound/llm).
"""
from __future__ import annotations

from domain.models import CovenantAnswer

COVENANT_CLAUSE_IDS = ("6.1", "6.2", "6.3")


def answers_from_raw(raw: dict) -> dict[str, CovenantAnswer]:
    out = {}
    for clause_id in COVENANT_CLAUSE_IDS:
        cell = raw.get(clause_id, {})
        out[clause_id] = CovenantAnswer(
            status=cell.get("status"),
            actual=cell.get("actual"),
            evidence_txn_id=cell.get("evidence_txn_id"),
            reasoning=cell.get("reasoning", ""),
        )
    return out
