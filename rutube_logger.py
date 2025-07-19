import logging
import tkinter as tk
from logging import Filter
from logging import LogRecord
from logging.handlers import RotatingFileHandler
from typing import Optional

import colorama
from colorama import Fore, Style

colorama.init()


class ColoredFormatter(logging.Formatter):
    """Форматтер с цветами для консоли"""
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.WHITE,
        # 'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, Fore.WHITE)
        message = super().format(record)
        return f"{color}{message}{Style.RESET_ALL}"


class GUILogHandler(logging.Handler):
    """Обработчик для вывода в Tkinter виджет с цветами"""

    def __init__(self, widget: tk.Text):
        super().__init__()
        self.widget = widget
        self.setFormatter(logging.Formatter('%(message)s'))
        self._setup_tags()

    def _setup_tags(self):
        self.widget.tag_config('DEBUG', foreground='cyan')
        self.widget.tag_config('INFO', foreground='black')
        self.widget.tag_config('WARNING', foreground='orange')
        self.widget.tag_config('ERROR', foreground='red')
        self.widget.tag_config('CRITICAL', foreground='red', font=('TkDefaultFont', 12, 'bold'))

    def emit(self, record: LogRecord):
        msg = self.format(record)
        self.widget.configure(state='normal')
        self.widget.insert(tk.END, msg + '\n', record.levelname)
        self.widget.see(tk.END)
        self.widget.configure(state='disabled')


class DownloadProgressFilter(Filter):
    """
    Фильтрует лишние DEBUG-сообщения от yt-dlp с прогрессом загрузки
    (оставляет в консоли и GUI, но скрывает в лог-файле).
    """

    def filter(self, record: LogRecord) -> bool:
        msg = record.getMessage()
        if record.levelno == logging.DEBUG and '[download]' in msg and 'ETA' in msg:
            return False
        return True


class UniversalLogger:
    """Универсальный логгер с расширенными возможностями"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.logger = logging.getLogger('RutubeLogger')
            self.logger.setLevel(logging.DEBUG)  # По умолчанию самый подробный уровень
            self._initialized = True

    def setup(self,
              log_file: Optional[str] = 'app.log',
              gui_widget: Optional[tk.Text] = None,
              max_log_size: int = 5 * 1024 * 1024,  # 5 MB
              backup_count: int = 3,
              log_level: str = 'INFO'):
        """Настройка обработчиков"""
        # Очистка старых обработчиков
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # Установка уровня логирования
        level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(level)

        # Форматтер для файлов
        formatter = logging.Formatter('[%(asctime)s] - %(levelname)s - %(message)s')

        # Файловый обработчик (только если указан log_file)
        if log_file:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_log_size,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(DownloadProgressFilter())  # ← добавили фильтр
            self.logger.addHandler(file_handler)

        # Консольный обработчик
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ColoredFormatter('%(message)s'))
        self.logger.addHandler(console_handler)

        # GUI обработчик (если передан)
        if gui_widget:
            gui_handler = GUILogHandler(gui_widget)
            gui_handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(gui_handler)

    def update_gui_handler(self, widget: tk.Text) -> None:
        """
        Обновляет только GUI обработчик, сохраняя другие настройки логгера

        Args:
            widget: Tkinter Text виджет для вывода логов
        """
        # Удаляем старый GUI обработчик, если он существует
        for handler in self.logger.handlers[:]:
            if isinstance(handler, GUILogHandler):
                self.logger.removeHandler(handler)

        # Создаем и добавляем новый GUI обработчик
        if widget:
            gui_handler = GUILogHandler(widget)
            gui_handler.setFormatter(logging.Formatter('%(message)s'))
            gui_handler.setLevel(self.logger.level)  # Сохраняем текущий уровень логирования
            self.logger.addHandler(gui_handler)

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def critical(self, message):
        self.logger.critical(message)


# Глобальный экземпляр логгера
logger = UniversalLogger()
