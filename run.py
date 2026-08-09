"""
Точка входа: python run.py --dataset agentic-bank-public --output submission.json

Сам пайплайн (гексагон: domain + application + adapters) живёт в src/.
Этот файл - тонкая обёртка композиционного корня, нужна только чтобы
сохранить прежний способ запуска (`docker compose run --rm agent`,
`python run.py --dry-run`), не трогая Dockerfile/docker-compose.yml.
"""
from __future__ import annotations
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
sys.path.insert(0, _SRC)

# Кэш PDF всегда рядом с этим файлом (<корень проекта>/cache) - ровно как
# в исходной версии, где cache_dir считался от os.path.dirname(run.py).
os.environ.setdefault("HALYK_CACHE_DIR", os.path.join(_ROOT, "cache"))

from adapters.inbound.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
