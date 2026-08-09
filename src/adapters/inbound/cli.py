"""
Inbound-адаптер (driving adapter): CLI-обёртка вокруг ProcessScenariosUseCase.

Точка входа: python run.py --dataset agentic-bank-public --output submission.json

Здесь и только здесь происходит "монтаж" гексагона: конкретные адаптеры
(pdfplumber, pandas, regex-классификатор, LLM-провайдер, JSON-файлы)
собираются и передаются в use case через порты.
"""
from __future__ import annotations
import argparse
import os

try:
    from dotenv import load_dotenv
    load_dotenv()  # подхватывает .env из текущей папки, если он есть - удобно в Windows,
                    # где `export $(cat .env | xargs)` из bash не работает
except ImportError:
    pass

from application.process_scenarios import ProcessScenariosUseCase
from adapters.outbound.pdf_document_repository import PdfplumberDocumentRepository
from adapters.outbound.regex_classifier import RegexDocumentClassifier
from adapters.outbound.pandas_ledger_repository import PandasLedgerRepository
from adapters.outbound.json_submission_repository import JsonSubmissionRepository
from adapters.outbound.llm.factory import build_reasoner


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default=os.environ.get("HALYK_DATASET_DIR", "agentic-bank-public"), help="папка с датасетом")
    p.add_argument("--output", default=os.environ.get("HALYK_OUTPUT_PATH", "submission.json"))
    p.add_argument("--team", default=os.environ.get("HALYK_TEAM_NAME", "your-team-name"))
    p.add_argument("--email", default=os.environ.get("HALYK_CONTACT_EMAIL", "you@example.com"))
    p.add_argument("--model", default=os.environ.get("HALYK_AGENT_MODEL", "claude-fable-5"))
    p.add_argument("--dry-run", action="store_true", help="прогнать пайплайн без вызовов LLM (проверка плюмбинга)")
    p.add_argument("--max-spend", type=float,
                    default=float(os.environ.get("HALYK_MAX_SPEND_USD", "3.0")),
                    help="жёсткий потолок расхода в USD за этот прогон - при достижении пайплайн "
                         "сохраняет прогресс и останавливается, не уходя в минус")
    p.add_argument("--no-resume", action="store_true",
                    help="пересчитать ВСЕ сценарии заново, даже если output-файл с прошлого "
                         "прогона уже существует (по умолчанию уже заполненные сценарии "
                         "пропускаются, чтобы не платить за них повторно)")
    return p


def main() -> None:
    args = _build_arg_parser().parse_args()

    # Кэш распарсенных PDF живёт рядом с run.py (тем же путём, что и раньше:
    # <корень проекта>/cache), чтобы docker-compose volume ./cache:/app/cache
    # продолжал работать без изменений. Корень проекта обычно прокидывает
    # HALYK_CACHE_DIR через run.py; если cli.py запущен напрямую - считаем
    # его сами (src/adapters/inbound/../../../cache).
    cache_dir = os.environ.get("HALYK_CACHE_DIR")
    if not cache_dir:
        inbound_dir = os.path.dirname(os.path.abspath(__file__))  # .../src/adapters/inbound
        cache_dir = os.path.normpath(os.path.join(inbound_dir, "..", "..", "..", "cache"))

    reasoner, _cfg = build_reasoner(args.model)

    use_case = ProcessScenariosUseCase(
        document_repository=PdfplumberDocumentRepository(cache_dir=cache_dir),
        classifier=RegexDocumentClassifier(),
        ledger_repository=PandasLedgerRepository(),
        reasoner=reasoner,
        submission_repository=JsonSubmissionRepository(),
    )

    use_case.run(
        dataset_dir=args.dataset,
        output_path=args.output,
        team=args.team,
        email=args.email,
        dry_run=args.dry_run,
        max_spend_usd=args.max_spend,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
