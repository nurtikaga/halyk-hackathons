"""Адаптер SubmissionRepositoryPort: чтение/запись submission.json и
submission_template.json на локальной файловой системе."""
from __future__ import annotations
import json
import os

from domain.ports import SubmissionRepositoryPort


class JsonSubmissionRepository(SubmissionRepositoryPort):
    def load_template(self, path: str) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def load_existing(self, path: str) -> dict | None:
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def save(self, path: str, submission: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(submission, f, ensure_ascii=False, indent=2)
