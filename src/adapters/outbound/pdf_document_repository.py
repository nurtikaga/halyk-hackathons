"""
Адаптер DocumentRepositoryPort: извлечение текста из PDF через pdfplumber,
с диск-кэшем (парсинг PDF не бесплатный по времени, а имена файлов - хеши,
так что перечитывать их на каждый прогон смысла нет).

Fallback на OCR оставлен как заглушка: в открытом датасете все документы -
текстовые PDF (pdfplumber справляется), но приватный датасет может содержать сканы.
"""
from __future__ import annotations
import glob
import hashlib
import os

import pdfplumber

from domain.ports import DocumentRepositoryPort

CACHE_VERSION = "v1"


class PdfplumberDocumentRepository(DocumentRepositoryPort):
    def __init__(self, cache_dir: str):
        self._cache_dir = cache_dir

    def _cache_path(self, pdf_path: str) -> str:
        h = hashlib.sha1((CACHE_VERSION + pdf_path).encode()).hexdigest()[:16]
        return os.path.join(self._cache_dir, f"{h}.txt")

    def _extract_pdf_text(self, pdf_path: str) -> str:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            text = "\n".join(pages)
        except Exception:  # noqa: BLE001
            text = ""
        if len(text.strip()) < 20:
            # Похоже на скан / нет текстового слоя -> нужен OCR/vision fallback.
            text = self._ocr_fallback(pdf_path)
        return text

    def _ocr_fallback(self, pdf_path: str) -> str:
        """
        Заглушка под OCR/vision. В открытом датасете не понадобилась ни разу
        (проверено на всех 200 файлах), но приватный датасет может содержать сканы.
        Реализация намеренно оставлена как TODO: подключить pytesseract или
        vision-модель (например, отправить страницы как изображения в Claude API).
        """
        return ""

    def load_all_documents(self, documents_dir: str) -> dict[str, str]:
        os.makedirs(self._cache_dir, exist_ok=True)
        out = {}
        for pdf_path in sorted(glob.glob(os.path.join(documents_dir, "*.pdf"))):
            cpath = self._cache_path(pdf_path)
            if os.path.exists(cpath):
                with open(cpath, encoding="utf-8") as f:
                    text = f.read()
            else:
                text = self._extract_pdf_text(pdf_path)
                with open(cpath, "w", encoding="utf-8") as f:
                    f.write(text)
            out[os.path.basename(pdf_path)] = text
        return out
