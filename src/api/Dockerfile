FROM python:3.11-slim

# рабочая директория внутри контейнера
WORKDIR /api

# отключаем кеш байткода и буферизацию вывода
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# копируем зависимости
COPY requirements.txt /api/requirements.txt
RUN pip install --no-cache-dir -r /api/requirements.txt

# копируем весь проект внутрь контейнера
COPY . /api

EXPOSE 8000

# запускаем uvicorn, main.py находится в /api/app/main.py
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
