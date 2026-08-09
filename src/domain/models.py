"""
Доменные модели: чистые структуры данных без зависимостей от инфраструктуры
(pandas, pdfplumber, HTTP-клиенты и т.п. сюда не импортируются).

Это ядро гексагональной архитектуры (hexagon core) - оно ничего не знает
о том, ЧЕМ документы распарсены, ГДЕ хранится леджер и КАКОЙ провайдер LLM
используется. Всё это - детали адаптеров, подключаемых через порты (см. ports.py).
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class DocInfo:
    """Результат классификации одного PDF-документа."""
    filename: str
    text: str
    account_ids: set[str] = field(default_factory=set)
    is_contract: bool = False
    is_superseded: bool = False
    is_draft: bool = False
    doc_type: str = "other"  # contract | audit | kyc | other
    covenant_period: tuple[str, str] | None = None
    covenants: dict[str, str] = field(default_factory=dict)  # "6.1" -> clause text


@dataclass
class TxnRecord:
    """Одна транзакция заёмщика, уже приведённая к JSON-сериализуемому виду."""
    txn_id: str
    date: str
    account_id: str
    counterparty: str
    description: str
    amount: float
    currency: str

    def to_dict(self) -> dict:
        return {
            "txn_id": self.txn_id,
            "date": self.date,
            "account_id": self.account_id,
            "counterparty": self.counterparty,
            "description": self.description,
            "amount": self.amount,
            "currency": self.currency,
        }


@dataclass
class LLMUsage:
    input_tokens: int
    output_tokens: int

    def as_dict(self) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}


@dataclass
class CovenantAnswer:
    status: str | None
    actual: float | None
    evidence_txn_id: str | None
    reasoning: str = ""
