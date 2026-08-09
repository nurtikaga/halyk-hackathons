"""
Локальный скоринг submission.json против ground_truth.json - ТОЧНО по формуле
из CASE.md (раздел 4. Оценка). Чистая доменная логика, не зависит от того,
откуда пришли submission/ground_truth (файл, API, тест) - это дело адаптера.
"""
from __future__ import annotations


def score_cell(pred: dict, key: dict) -> tuple[float, dict]:
    breakdown = {"status": 0.0, "actual": 0.0, "evidence": 0.0}

    if pred.get("status") not in ("COMPLIANT", "BREACH"):
        return 0.0, breakdown
    if pred["status"] != key["status"]:
        return 0.0, breakdown
    breakdown["status"] = 0.50

    actual_pred = pred.get("actual")
    actual_key = key["actual"]
    actual_score = 0.0
    if isinstance(actual_pred, (int, float)) and actual_key != 0:
        e = abs(actual_pred - actual_key) / abs(actual_key)
        actual_score = 0.30 * max(0.0, 1 - e / 0.05)
    breakdown["actual"] = actual_score

    evidence_key = key.get("evidence_txn_id")
    evidence_score = 0.0
    if evidence_key is None:
        # баллы за evidence "убывают вместе с actual по той же шкале"
        evidence_score = (actual_score / 0.30) * 0.20 if actual_score else 0.0
    else:
        if pred.get("evidence_txn_id") == evidence_key:
            evidence_score = 0.20
    breakdown["evidence"] = evidence_score

    return breakdown["status"] + breakdown["actual"] + breakdown["evidence"], breakdown


def score_submission(submission: dict, ground_truth: dict) -> tuple[float, int, list[str]]:
    """Возвращает (total, n, лог построчного вывода) - логика main() из validate.py,
    вынесенная из CLI, чтобы адаптер отвечал только за argparse/print."""
    gt_scenarios = ground_truth["scenarios"]
    total, n = 0.0, 0
    log_lines: list[str] = []

    for scenario_id, scenario_data in gt_scenarios.items():
        covenants = scenario_data["covenants"]
        pred_scn = submission.get("answers", {}).get(scenario_id, {})
        log_lines.append(f"\n=== {scenario_id} ===")
        for clause_id, key in covenants.items():
            pred = pred_scn.get(clause_id, {})
            score, breakdown = score_cell(pred, key)
            total += score
            n += 1
            log_lines.append(
                f"  {clause_id}: {score:.3f}  "
                f"(status={breakdown['status']:.2f} actual={breakdown['actual']:.2f} "
                f"evidence={breakdown['evidence']:.2f})  "
                f"pred={pred.get('status')}/{pred.get('actual')} "
                f"key={key['status']}/{key['actual']}"
            )

    return total, n, log_lines
