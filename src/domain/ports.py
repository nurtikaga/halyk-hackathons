"""
Порты (Ports & Adapters): абстрактные интерфейсы, которые описывают, ЧТО
нужно бизнес-логике (application/pipeline.py), но не ГДЕ и КАК это реализовано.

Каждый порт здесь - это "розетка" на границе гексагона. Конкретные "вилки"
(адаптеры) живут в adapters/outbound/*: pdfplumber, pandas, requests/anthropic,
JSON-файлы на диске и т.д. Ядро (domain, application) импортирует ТОЛЬКО эти
абстракции и никогда - конкретные библиотеки инфраструктуры.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from domain.models import DocInfo, TxnRecord, LLMUsage


class DocumentRepositoryPort(ABC):
    """Извлечение текста документов заёмщиков (в текущей реализации - PDF)."""

    @abstractmethod
    def load_all_documents(self, documents_dir: str) -> dict[str, str]:
        """filename -> extracted text, для всех документов в documents_dir."""
        raise NotImplementedError


class DocumentClassifierPort(ABC):
    """Классификация документов и отбор действующих версий."""

    @abstractmethod
    def classify_all(self, texts: dict[str, str]) -> dict[str, DocInfo]:
        raise NotImplementedError

    @abstractmethod
    def select_active_contract(self, docs: list[DocInfo]) -> DocInfo | None:
        raise NotImplementedError

    @abstractmethod
    def select_supporting_docs(self, docs: list[DocInfo]) -> list[DocInfo]:
        raise NotImplementedError


class LedgerRepositoryPort(ABC):
    """Доступ к реестру транзакций (master_ledger_*.csv в текущей реализации)."""

    @abstractmethod
    def load(self, path: str) -> object:
        """Загружает леджер и возвращает непрозрачный handle для остальных методов порта."""
        raise NotImplementedError

    @abstractmethod
    def build_account_scenario_map(self, ledger: object, valid_scenarios: set[str]) -> dict[str, str]:
        """account_id -> scenario_id, только для нужных сценариев."""
        raise NotImplementedError

    @abstractmethod
    def txns_for_scenario(
        self,
        ledger: object,
        scenario_id: str,
        period: tuple[str, str] | None = None,
    ) -> list[TxnRecord]:
        """Транзакции сценария, опционально отфильтрованные по периоду [start, end]."""
        raise NotImplementedError


class LLMReasonerPort(ABC):
    """
    Единственная точка, где домен просит содержательный вывод у LLM.
    Реализация (какой провайдер, какой формат запроса) - деталь адаптера.
    """

    @abstractmethod
    def build_prompt(
        self,
        scenario_id: str,
        covenant_clauses: dict[str, str],
        supporting_texts: list[tuple[str, str]],
        ledger_rows: list[dict],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def call(self, prompt: str) -> tuple[dict, LLMUsage]:
        """Возвращает (распарсенный JSON-ответ модели, usage)."""
        raise NotImplementedError

    @abstractmethod
    def estimate_cost_usd(self, usage: LLMUsage) -> float | None:
        """None, если провайдер тарифицируется не по токенам (напр. compute-time billing)."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def pricing_per_million(self) -> tuple[float, float] | None:
        """(price_in, price_out) за 1М токенов для текущей модели, если применимо."""
        raise NotImplementedError


class SubmissionRepositoryPort(ABC):
    """Чтение шаблона/черновика ответа и сохранение submission.json."""

    @abstractmethod
    def load_template(self, path: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def load_existing(self, path: str) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, path: str, submission: dict) -> None:
        raise NotImplementedError
