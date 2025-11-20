FROM python:3.10-slim

LABEL authors="MartisArch"

# Установка зависимостей системы
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Создание папки для данных MongoDB
RUN mkdir -p /data/db

# Установка рабочей директории
WORKDIR /app

# Копирование файлов проекта
COPY . /app

# Установка зависимостей Python
RUN pip install --no-cache-dir -r requirements.txt

# Указание портов для приложения и MongoDB
EXPOSE 8080
EXPOSE 27017

# Запуск MongoDB и приложения
CMD ["python", "main.py"]
