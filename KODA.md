# KODA.md

## Архитектура

Проект переписан в стиле **OOP + modular**.

### Модули
- `rutube_gui.py` — GUI и обработчики действий пользователя
- `rutube_downloader.py` — класс `RutubeDownloader`, связывает получение списка и скачивание
- `rutube_gateway.py` — работа с Rutube: Selenium для списка, yt-dlp для метаданных
- `rutube_storage.py` — сохранение файлов, превью, CSV, открытие mp4
- `rutube_models.py` — модели `VideoMetadata`, `AppSettings`, `DownloadStatus`
- `rutube_config.py` — сохранение настроек в `rutube_config.json`
- `rutube_logger.py` — логирование в файл, консоль и GUI

## Правила
- Список видео канала получать через Selenium
- `yt-dlp` использовать для метаданных и скачивания видео
- GUI не должен напрямую работать с Selenium или `yt-dlp`
- Потоковые обновления GUI делать через `widget.after(...)`
