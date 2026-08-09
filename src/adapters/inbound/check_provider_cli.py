"""Inbound-адаптер: небольшой diagnостический CLI, который печатает, какой
провайдер/модель/base_url будут использованы, и (для OpenAI-совместимых
шлюзов) пингует GET /models."""
from __future__ import annotations
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

from adapters.outbound.llm.provider_detection import detect_provider


def main() -> None:
    cfg = detect_provider()

    print(f"MODEL     = {cfg.model}")
    print(f"PROVIDER  = {cfg.provider}")
    print(f"BASE_URL  = {cfg.base_url}")
    print(
        f"API_KEY   = "
        f"{'задан (' + cfg.api_key[:8] + '...)' if cfg.api_key else 'НЕ ЗАДАН'}"
    )
    print()

    if cfg.provider == "anthropic":
        print("Провайдер: Anthropic API — отдельная проверка /models не выполняется.")
        sys.exit(0)

    if not cfg.base_url:
        print("! HALYK_API_BASE_URL не задан.")
        sys.exit(1)

    url = f"{cfg.base_url.rstrip('/')}/models"

    headers = {
        "Content-Type": "application/json",
    }

    # Modal custom endpoint работает без Bearer auth.
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    print(f"Пробую GET {url} ...")

    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=60,
        )

        print(f"HTTP статус: {resp.status_code}")
        print(f"Тело ответа (первые 500 симв.): {resp.text[:500]}")

        if resp.status_code == 200:
            print()
            print("✓ Endpoint и base_url рабочие.")
        elif resp.status_code == 401:
            print()
            print("! 401 Unauthorized — endpoint требует authentication.")
        else:
            print()
            print(f"! Неожиданный статус {resp.status_code}.")

    except requests.RequestException as e:
        print(f"! Сетевая ошибка: {e}")


if __name__ == "__main__":
    main()
