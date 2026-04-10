# Rutube Downloader

Версия с более простой архитектурой: OOP + modular.

## Структура

- `main.py` — точка входа
- `app/rutube_gui.py` — интерфейс на Tkinter
- `app/rutube_downloader.py` — оркестрация загрузки и статусов
- `app/rutube_gateway.py` — Selenium для списка, yt-dlp для метаданных
- `app/rutube_storage.py` — работа с файлами
- `app/rutube_models.py` — модели и статусы
- `app/rutube_config.py` — загрузка и сохранение настроек
- `app/rutube_logger.py` — логирование в консоль, файл и GUI

## Запуск

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Или через `start.cmd`.
