@echo off
if not exist .venv (
    echo [*] Создание виртуального окружения...
    python -m venv .venv
)

echo [*] Активация окружения...
call .venv\Scripts\activate

echo [*] Установка зависимостей...
python -m pip install .
if errorlevel 1 exit /b 1

echo [*] Запуск приложения...
python main.py

pause
