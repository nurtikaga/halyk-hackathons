"""
Построение промпта для проверки ковенантов. Дизайн специально узкий: на вход
модель получает НЕ весь договор (25 статей), а только:
  1) уже вырезанные regex'ом пункты 6.1/6.2/6.3 (см. adapters/outbound/regex_classifier.py)
  2) финальные (не-draft) аудиторские/KYC документы того же заёмщика
  3) отфильтрованные по account_id и covenant-периоду транзакции из леджера

Модель не придумывает числа "из головы" - ей explicitly велено опираться
только на приведённые данные и указывать evidence.

Это адаптерная деталь (конкретный контракт промпт/ответ конкретной LLM),
поэтому живёт в adapters/outbound/llm, а не в domain/application.
"""
from __future__ import annotations
import json

SYSTEM_PROMPT = """Ты — финансовый аналитик банка. Тебе даны:
  - точный текст 3 пунктов финансовых ковенантов (6.1, 6.2, 6.3) из кредитного договора заёмщика;
  - финальные аудиторские документы и/или KYC/комплаенс-досье этого же заёмщика (если есть);
  - список транзакций этого заёмщика из реестра за нужный период (JSON).

Для КАЖДОГО из пунктов 6.1, 6.2, 6.3 определи:
  - status: "COMPLIANT" или "BREACH"
  - actual: фактическое значение показателя, ВСЕГДА положительное число, 2 знака после запятой.
    Суммы - в долларах, коэффициенты - обычным числом (1.68, не "1.68x").
  - evidence_txn_id: ID ЕДИНСТВЕННОЙ транзакции, чьё включение/исключение/переклассификация
    меняет вердикт, ИЛИ null, если результат определяется не одной транзакцией (коэффициент,
    агрегатная сумма без одной решающей операции). НЕ указывай "самую крупную" транзакцию
    просто потому что она большая - только если её удаление реально меняет status.
  - reasoning: краткое обоснование на 1-2 предложения (не больше) со ссылкой на
    конкретный источник (документ + пункт/раздел) и явно показанным вычислением
    (какие числа, какая формула). Не пересказывай контекст - только суть расчёта.

Используй ТОЛЬКО данные, которые тебе передали. Если данных не хватает для точного расчёта -
дай наилучшую оценку на основе того, что есть, и явно отметь это в reasoning.

Ответь СТРОГО в формате JSON, без markdown-разметки, без пояснений вне JSON:
{
  "6.1": {"status": "...", "actual": 0.0, "evidence_txn_id": null, "reasoning": "..."},
  "6.2": {"status": "...", "actual": 0.0, "evidence_txn_id": null, "reasoning": "..."},
  "6.3": {"status": "...", "actual": 0.0, "evidence_txn_id": null, "reasoning": "..."}
}"""


def build_scenario_bundle_prompt(
    scenario_id: str,
    covenant_clauses: dict[str, str],
    supporting_texts: list[tuple[str, str]],  # (filename, text)
    ledger_rows: list[dict],
    max_chars_per_doc: int = 12000,
) -> str:
    parts = [f"# Заёмщик: сценарий {scenario_id}\n"]

    parts.append("## Пункты финансовых ковенантов (из действующего договора)\n")
    for clause_id in ("6.1", "6.2", "6.3"):
        text = covenant_clauses.get(clause_id, "(не найден)")
        parts.append(f"### Пункт {clause_id}\n{text}\n")

    if supporting_texts:
        parts.append("\n## Подтверждающие документы (аудит / KYC, финальные версии)\n")
        for fname, text in supporting_texts:
            # Защита от неожиданно длинных документов - обрезаем, а не отправляем
            # как есть, чтобы один "раздутый" документ не взорвал стоимость вызова.
            truncated = text[:max_chars_per_doc]
            note = "" if len(text) <= max_chars_per_doc else \
                f"\n[... документ обрезан, показано {max_chars_per_doc} из {len(text)} символов ...]"
            parts.append(f"### Документ: {fname}\n{truncated}{note}\n")

    parts.append(f"\n## Транзакции заёмщика за период ({len(ledger_rows)} шт., JSON)\n")
    parts.append(json.dumps(ledger_rows, ensure_ascii=False, indent=2))

    return "\n".join(parts)


def extract_json(raw: str) -> dict:
    raw = raw.strip()
    raw = raw.removeprefix("```json").removeprefix("```")
    if raw.endswith("```"):
        raw = raw[: -len("```")]
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"В ответе модели не найден JSON-объект. Начало ответа: {raw[:200]!r}")
    return json.loads(raw[start:end + 1])
