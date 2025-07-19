# Version:0.6
from rutube_logger import logger
from rutube_downloader import RutubeDownloader
from rutube_gui import create_gui

if __name__ == "__main__":
    # Настройка логгера (один раз при запуске приложения)
    logger.setup(
        log_file='rutube_app.log',
        gui_widget=None,  # Будет установлен позже в GUI
        max_log_size=10 * 1024 * 1024,  # 10 MB
        backup_count=5,
        log_level='DEBUG'  # 'INFO' в продакшене
    )
    downloader = RutubeDownloader()
    create_gui(downloader)
