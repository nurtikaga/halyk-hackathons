# Лёгкий образ - нужен только Python + pdfplumber/pandas/anthropic,
# без GPU и тяжёлых зависимостей.
FROM python:3.11-slim

# pdfplumber тянет за собой Pillow/pdfminer, которым иногда нужны системные
# либы для работы со шрифтами - ставим по минимуму, чтобы не раздувать образ.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY run.py .

# Датасет и .env НЕ кладём в образ (см. .dockerignore) - они монтируются
# как volume при запуске, чтобы:
#  1) не пересобирать образ при смене датасета (открытый -> приватный 9 августа)
#  2) не запечь API-ключ внутрь образа
RUN mkdir -p /app/cache /app/output

# Дефолтные пути ПОД структуру volume'ов из docker-compose.yml. Важно: если
# запускать `docker compose run agent --dry-run` (с доп. флагами), Docker
# заменяет весь CMD целиком - поэтому пути заданы через ENV (их run.py
# читает как дефолты для --dataset/--output), а не только через CMD,
# и не теряются при любых дополнительных флагах.
ENV HALYK_DATASET_DIR=/app/data
ENV HALYK_OUTPUT_PATH=/app/output/submission.json

ENTRYPOINT ["python", "run.py"]
