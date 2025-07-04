from .settings import *  # Наследуем всё из основного settings.py

# Используем SQLite вместо PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',  # Или 'C:/Dima/Programming/My_projects/Jango_rent/db.sqlite3' для явности
    }
}

# Включаем режим отладки
DEBUG = True

# Хосты, которым разрешён доступ — для локалки можно '*'
ALLOWED_HOSTS = ['*']