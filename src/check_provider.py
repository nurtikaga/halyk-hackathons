"""Тонкая обёртка для сохранения прежнего способа запуска: python src/check_provider.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters.inbound.check_provider_cli import main  # noqa: E402

if __name__ == "__main__":
    main()
