#!/usr/bin/env bash
# Build script for Render.com

# Установить зависимости
pip install -r requirements.txt

# Применить миграции
python manage.py migrate

# Собрать статику
python manage.py collectstatic --noinput
