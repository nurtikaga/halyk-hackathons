"""
Адаптер LedgerRepositoryPort: загрузка master_ledger_2025.csv через pandas
и построение связей account_id <-> scenario_id.

Ключевая идея (из CASE.md):
  - txn_id имеет вид TXN-{scenario_id}-{seq}, например TXN-P1-0039
  - Значит scenario_id транзакции читается прямо из её ID.
  - account_id -> ровно один scenario_id (проверяется).
  - В леджере есть МНОГО "чужих" scenario-префиксов (шум/дистракторы) -
    их нужно игнорировать, работаем только с scenario_id, которые
    реально есть в submission_template.json.

pandas - деталь ЭТОГО адаптера: application-слой получает и отдаёт только
доменные TxnRecord/dict, а не DataFrame.
"""
from __future__ import annotations
import re
import pandas as pd

from domain.models import TxnRecord
from domain.ports import LedgerRepositoryPort

TXN_SCENARIO_RE = re.compile(r"^TXN-([A-Z0-9]+)-")


class PandasLedgerRepository(LedgerRepositoryPort):
    def load(self, path: str) -> pd.DataFrame:
        df = pd.read_csv(path, encoding="utf-8")
        df["scenario_id"] = df["txn_id"].str.extract(TXN_SCENARIO_RE)
        df["date"] = pd.to_datetime(df["date"])
        df["amount"] = df["amount"].astype(float)
        return df

    def build_account_scenario_map(self, ledger: pd.DataFrame, valid_scenarios: set[str]) -> dict[str, str]:
        """account_id -> scenario_id, restricted to scenarios we actually need to answer."""
        sub = ledger[ledger["scenario_id"].isin(valid_scenarios)]
        mapping = sub.groupby("account_id")["scenario_id"].unique().to_dict()
        out = {}
        for acc, scns in mapping.items():
            if len(scns) != 1:
                raise ValueError(f"account_id {acc} maps to multiple scenarios: {scns}")
            out[acc] = scns[0]
        return out

    def txns_for_scenario(
        self,
        ledger: pd.DataFrame,
        scenario_id: str,
        period: tuple[str, str] | None = None,
    ) -> list[TxnRecord]:
        txns = ledger[ledger["scenario_id"] == scenario_id].copy()
        if period:
            start, end = period
            txns = txns[(txns["date"] >= start) & (txns["date"] <= end)]

        cols = ["txn_id", "date", "account_id", "counterparty", "description", "amount", "currency"]
        rows = txns[cols].copy()
        rows["date"] = rows["date"].astype(str)

        return [TxnRecord(**row) for row in rows.to_dict(orient="records")]
