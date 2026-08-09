"""
Inbound-адаптер: локальный скоринг submission.json против ground_truth.json.
Полезно прогонять на открытых 12 сценариях ДО того как появится приватный датасет.

Запуск:
    python src/validate.py --submission submission.json --ground-truth agentic-bank-public/ground_truth.json
"""
from __future__ import annotations
import argparse
import json

from application.scoring import score_submission


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--submission", required=True)
    p.add_argument("--ground-truth", required=True)
    args = p.parse_args()

    sub = json.load(open(args.submission, encoding="utf-8"))
    gt = json.load(open(args.ground_truth, encoding="utf-8"))

    total, n, log_lines = score_submission(sub, gt)

    for line in log_lines:
        print(line)

    print(f"\nИТОГО: {total:.2f} / {n} ячеек, средний балл {total/n:.3f} (макс. 1.0 на ячейку)")


if __name__ == "__main__":
    main()
