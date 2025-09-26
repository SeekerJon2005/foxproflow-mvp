# Базовый образ
FROM python:3.12-slim

# Настройки Python: без .pyc и с немедленным выводом логов
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Рабочая директория внутри контейнера
WORKDIR /app

# Установим пакеты для сборки (иногда нужны для lxml, psycopg2, scipy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Скопируем requirements.txt и установим зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Скопируем весь проект в контейнер
COPY . .

# Порт, который будет слушать uvicorn
EXPOSE 8080

# Команда по умолчанию (перезаписывается в docker-compose.yml)
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
