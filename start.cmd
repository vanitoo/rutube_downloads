@echo off
if not exist .venv (
    echo [*] Создание виртуального окружения...
    python -m venv .venv
)

echo [*] Активация окружения...
call .venv\Scripts\activate

echo [*] Установка зависимостей...
pip install -r requirements.txt

echo [*] Запуск приложения...
python main.py

pause
