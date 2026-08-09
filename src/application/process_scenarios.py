"""
Application layer / use case: тот же пайплайн, что раньше жил в run.py::run(),
но теперь он общается с внешним миром ИСКЛЮЧИТЕЛЬНО через порты
(domain.ports.*), а не через pdfplumber/pandas/anthropic напрямую.

Шаги:
  1. Загрузить леджер, построить account_id -> scenario_id.
  2. Извлечь текст всех документов (через DocumentRepositoryPort, с кэшем внутри адаптера).
  3. Классифицировать документы, сгруппировать по сценарию.
  4. Для каждого сценария: выбрать действующий договор (не superseded),
     финальные (не draft) аудит/KYC документы, отфильтровать транзакции периода.
  5. Вызвать LLM (LLMReasonerPort) на каждый сценарий -> 3 ковенанта.
  6. Собрать submission.json СТРОГО по форме submission_template.json.
"""
from __future__ import annotations
import collections
import copy
import os

from domain.answers import answers_from_raw
from domain.models import LLMUsage
from domain.ports import (
    DocumentClassifierPort,
    DocumentRepositoryPort,
    LedgerRepositoryPort,
    LLMReasonerPort,
    SubmissionRepositoryPort,
)


def _cell_is_filled(cell: dict) -> bool:
    return cell.get("status") is not None


class ProcessScenariosUseCase:
    """Оркестрирует весь пайплайн через порты, инжектированные в конструктор."""

    def __init__(
        self,
        document_repository: DocumentRepositoryPort,
        classifier: DocumentClassifierPort,
        ledger_repository: LedgerRepositoryPort,
        reasoner: LLMReasonerPort,
        submission_repository: SubmissionRepositoryPort,
    ):
        self._documents = document_repository
        self._classifier = classifier
        self._ledger = ledger_repository
        self._reasoner = reasoner
        self._submissions = submission_repository

    def _build_scenario_prompt(self, scenario_id, contract, supporting, ledger, dataset_max_chars=12000):
        covenant_clauses = contract.covenants if contract else {}
        supporting_texts = [(d.filename, d.text) for d in supporting]

        for fname, text in supporting_texts:
            if len(text) > dataset_max_chars:
                print(f"    ! {fname}: {len(text)} символов, будет обрезан до {dataset_max_chars} "
                      f"перед отправкой в LLM (см. адаптер LLMReasonerPort.build_prompt)")

        period = contract.covenant_period if contract else None
        txns = self._ledger.txns_for_scenario(ledger, scenario_id, period=period)
        ledger_rows = [t.to_dict() for t in txns]

        return self._reasoner.build_prompt(scenario_id, covenant_clauses, supporting_texts, ledger_rows)

    def run(
        self,
        dataset_dir: str,
        output_path: str,
        team: str,
        email: str,
        dry_run: bool = False,
        max_spend_usd: float = 3.0,
        resume: bool = True,
    ) -> None:
        ledger_path = os.path.join(dataset_dir, "master_ledger_2025.csv")
        docs_dir = os.path.join(dataset_dir, "documents")
        template_path = os.path.join(dataset_dir, "submission_template.json")

        template = self._submissions.load_template(template_path)
        valid_scenarios = set(template["answers"].keys())

        ledger = self._ledger.load(ledger_path)
        acc2scn = self._ledger.build_account_scenario_map(ledger, valid_scenarios)

        print(f"[1/4] Извлекаю текст {docs_dir} ...")
        texts = self._documents.load_all_documents(docs_dir)

        print(f"[2/4] Классифицирую {len(texts)} документов ...")
        docs = self._classifier.classify_all(texts)

        by_scn = collections.defaultdict(list)
        for d in docs.values():
            for acc in d.account_ids:
                if acc in acc2scn:
                    by_scn[acc2scn[acc]].append(d)

        # RESUME: если output_path уже существует (например, прошлый прогон прервался
        # по бюджету/ошибке) - берём его как базу и НЕ пересчитываем уже заполненные
        # ячейки. Это критично для стоимости: без этого каждый повторный запуск
        # платит заново за все сценарии, включая уже успешно посчитанные.
        submission = None
        if resume:
            submission = self._submissions.load_existing(output_path)
            if submission is not None:
                print(f"[resume] Найден существующий {output_path}, продолжаю с него "
                      f"(уже заполненные сценарии пересчитываться не будут)")
        if submission is None:
            submission = copy.deepcopy(template)

        submission["team"] = team
        submission["contact_email"] = email
        submission["model"] = self._reasoner.model

        def save():
            self._submissions.save(output_path, submission)

        pricing = self._reasoner.pricing_per_million
        price_in, price_out = pricing if pricing else (10, 50)
        total_cost = 0.0
        # Некоторые провайдеры (например, Modal Auto Endpoint) тарифицируются по
        # времени работы контейнера, а не по токенам - estimate_cost_usd() для них
        # возвращает None. В этом случае бюджетный контроль по $-оценке токенов
        # физически бессмысленен (мы не знаем реальную цену вызова заранее) -
        # отключаем и pre-call проверку, и накопление total_cost, печатаем
        # предупреждение один раз.
        cost_tracking_enabled = self._reasoner.estimate_cost_usd(LLMUsage(0, 0)) is not None
        if not cost_tracking_enabled:
            print(f"  ! Провайдер модели {self._reasoner.model!r} тарифицируется не по токенам "
                  f"(estimate_cost_usd вернул None) - автоматический контроль бюджета "
                  f"(--max-spend) ОТКЛЮЧЕН для этого прогона. Следите за расходом в "
                  f"личном кабинете провайдера вручную.")

        print(f"[3/4] Обрабатываю {len(valid_scenarios)} сценариев "
              f"(бюджет: ${max_spend_usd:.2f}, модель: {self._reasoner.model}, "
              f"${price_in}/${price_out} за 1М ток.) ...")
        for scenario_id in sorted(valid_scenarios):
            scn_answers = submission["answers"].get(scenario_id, {})
            if resume and scn_answers and all(_cell_is_filled(c) for c in scn_answers.values()):
                print(f"  = {scenario_id}: уже посчитан в предыдущем прогоне, пропускаю (без затрат)")
                continue

            scn_docs = by_scn.get(scenario_id, [])
            contract = self._classifier.select_active_contract(scn_docs)
            supporting = self._classifier.select_supporting_docs(scn_docs)

            if contract is None:
                print(f"  ! {scenario_id}: активный договор не найден, пропуск (останется null)")
                continue

            prompt = self._build_scenario_prompt(scenario_id, contract, supporting, ledger)

            if dry_run:
                print(f"  {scenario_id}: dry-run, пропускаю вызов LLM "
                      f"(промпт {len(prompt)} символов, {len(supporting)} доп. документов)")
                continue

            if cost_tracking_enabled:
                # Худшая оценка стоимости ЭТОГО вызова (input по факту символов, output - по
                # лимиту max_tokens, то есть максимум, что может списаться) - проверяем
                # ДО вызова, чтобы не уйти в минус посреди API-запроса.
                est_input_tokens = len(prompt) / 4 + 500  # +500 на системный промпт
                worst_case_call_cost = (est_input_tokens * price_in + 8000 * price_out) / 1e6
                if total_cost + worst_case_call_cost > max_spend_usd:
                    print(f"  ! СТОП: бюджет ${max_spend_usd:.2f} исчерпан "
                          f"(потрачено ${total_cost:.2f}, следующий вызов может стоить до "
                          f"${worst_case_call_cost:.2f}). Сохраняю прогресс и останавливаюсь.")
                    save()
                    print(f"  Уже посчитанные сценарии сохранены в {output_path}. "
                          f"Запустите ещё раз (без --no-resume) после пополнения баланса - "
                          f"пересчитываться будут только оставшиеся.")
                    return

            try:
                raw, usage = self._reasoner.call(prompt)
                answers = answers_from_raw(raw)
                call_cost = self._reasoner.estimate_cost_usd(usage)
                if call_cost is not None:
                    total_cost += call_cost
            except Exception as e:  # noqa: BLE001
                print(f"  ! {scenario_id}: ошибка LLM ({e}), ячейки останутся null")
                continue

            for clause_id, ans in answers.items():
                if clause_id not in submission["answers"][scenario_id]:
                    continue  # не создаём новых ключей - только заполняем шаблон
                submission["answers"][scenario_id][clause_id] = {
                    "status": ans.status,
                    "actual": ans.actual,
                    "evidence_txn_id": ans.evidence_txn_id,
                }
            save()  # сохраняем после КАЖДОГО сценария - оплаченный результат никогда не теряется
            cost_note = f"вызов ${call_cost:.3f}, всего потрачено ${total_cost:.2f}" if cost_tracking_enabled \
                else "стоимость неизвестна (compute-time billing, см. личный кабинет провайдера)"
            print(f"  ✓ {scenario_id}  ({cost_note})")

        final_cost_note = f"${total_cost:.2f}" if cost_tracking_enabled else "неизвестен (compute-time billing)"
        print(f"[4/4] Готово. Итоговый расход: {final_cost_note}. Файл: {output_path}")
