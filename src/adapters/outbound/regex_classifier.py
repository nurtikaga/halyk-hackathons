"""
Адаптер DocumentClassifierPort: классификация документов и извлечение
структурных фактов регулярками - БЕЗ LLM, потому что документы (в открытом
датасете) хорошо структурированы: заголовки "Статья N", "Пункт N.N",
маркеры устаревшей версии - всё это надёжнее и дешевле достать regex'ом,
чем гонять модель по 15 страницам текста.

Это ровно то место, где при необходимости можно подключить другую реализацию
DocumentClassifierPort (например, LLM-классификатор) не трогая остальной пайплайн.
"""
from __future__ import annotations
import re

from domain.models import DocInfo
from domain.ports import DocumentClassifierPort

ACC_RE = re.compile(r"ACC-\d{4}")
SUPERSEDED_RE = re.compile(r"НЕДЕЙСТВУЮЩАЯ РЕДАКЦИЯ|НЕ ПРИМЕНЯЕТСЯ|заменена и изложена в новой редакции", re.I)
CONTRACT_RE = re.compile(r"ДОГОВОР БАНКОВСКОГО ЗАЙМА")
# Черновики/промежуточные версии аудиторских документов - тоже нужно отличать от финальных,
# ровно как и версии договора. Пример реальной формулировки из датасета:
# "ПРОЕКТ — ПРОМЕЖУТОЧНАЯ ВЕДОМОСТЬ ... ЗАМЕНЕНА ОКОНЧАТЕЛЬНЫМ ОТЧЁТОМ ... НЕ ЯВЛЯЕТСЯ
#  ОКОНЧАТЕЛЬНОЙ ПОЗИЦИЕЙ АУДИТОРА"
DRAFT_RE = re.compile(
    r"ПРОЕКТ\s*[—-]\s*ПРОМЕЖУТОЧН|НЕ\s+ЯВЛЯЕТСЯ\s+ОКОНЧАТЕЛЬНОЙ\s+ПОЗИЦИЕЙ", re.I
)
FINAL_POSITION_RE = re.compile(
    r"окончательн\w+ позици\w+ аудитора для целей проверки ковенант", re.I
)
COVENANT_ARTICLE_RE = re.compile(r"Статья\s*6\s*[—-]\s*Финансовые ковенанты(.*?)Статья\s*7", re.S)
COVENANT_CLAUSE_RE = re.compile(
    r"Пункт\s*(6\.\d+)\s+(.*?)(?=Пункт\s*6\.\d+|\Z)", re.S
)
DATE_RANGE_RE = re.compile(r"с\s*(\d{4}-\d{2}-\d{2})\s*по\s*(\d{4}-\d{2}-\d{2})")
BORROWER_ACCOUNT_RE = re.compile(r"банковский счёт\s*(ACC-\d{4})")
CONTRACT_DATE_RE = re.compile(r"от\s+(\d{1,2}\s+\S+\s+\d{4}\s+года)")


class RegexDocumentClassifier(DocumentClassifierPort):
    def _classify_document(self, filename: str, text: str) -> DocInfo:
        info = DocInfo(filename=filename, text=text)
        info.account_ids = set(ACC_RE.findall(text))
        info.is_superseded = bool(SUPERSEDED_RE.search(text[:500]))
        info.is_contract = bool(CONTRACT_RE.search(text))
        info.is_draft = bool(DRAFT_RE.search(text[:600])) and not bool(FINAL_POSITION_RE.search(text[:2000]))

        low_head = text[:3000].lower()
        if info.is_contract:
            info.doc_type = "contract"
        elif "аудит" in low_head or "заключение аудитора" in low_head:
            info.doc_type = "audit"
        elif "kyc" in low_head or "комплаенс-досье" in low_head or "связанные стороны" in low_head:
            info.doc_type = "kyc"
        else:
            info.doc_type = "other"

        m = DATE_RANGE_RE.search(text[:2500])
        if m:
            info.covenant_period = (m.group(1), m.group(2))

        if info.is_contract:
            art = COVENANT_ARTICLE_RE.search(text)
            if art:
                body = art.group(1)
                for clause_id, clause_text in COVENANT_CLAUSE_RE.findall(body):
                    info.covenants[clause_id] = clause_text.strip()

        return info

    def classify_all(self, texts: dict[str, str]) -> dict[str, DocInfo]:
        return {fname: self._classify_document(fname, txt) for fname, txt in texts.items()}

    def select_active_contract(self, docs: list[DocInfo]) -> DocInfo | None:
        """Среди документов одного заёмщика выбрать ДЕЙСТВУЮЩИЙ договор (не superseded)."""
        contracts = [d for d in docs if d.is_contract]
        active = [d for d in contracts if not d.is_superseded]
        if active:
            # если вдруг несколько "активных" - берём с более поздним периодом начала
            active.sort(key=lambda d: d.covenant_period[0] if d.covenant_period else "", reverse=True)
            return active[0]
        return contracts[0] if contracts else None

    def select_supporting_docs(self, docs: list[DocInfo]) -> list[DocInfo]:
        """
        Аудит/KYC документы для передачи в LLM: исключаем черновики/промежуточные версии
        (is_draft=True), берём только финальные позиции - ровно как с superseded контрактами.
        """
        out = []
        for d in docs:
            if d.doc_type in ("audit", "kyc") and not d.is_draft:
                out.append(d)
        return out
