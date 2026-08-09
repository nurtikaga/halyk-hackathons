"""Тонкая обёртка для сохранения прежнего способа запуска:
python src/validate.py --submission submission.json --ground-truth agentic-bank-public/ground_truth.json"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters.inbound.validate_cli import main  # noqa: E402

if __name__ == "__main__":
    main()
