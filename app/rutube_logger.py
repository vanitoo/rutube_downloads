from __future__ import annotations

import logging
import tkinter as tk
from logging.handlers import RotatingFileHandler
from pathlib import Path


class TkTextHandler(logging.Handler):
    def __init__(self, widget: tk.Text):
        super().__init__()
        self.widget = widget
        self.setFormatter(logging.Formatter('%(message)s'))

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.widget.after(0, self._append, message, record.levelname)

    def _append(self, message: str, level_name: str) -> None:
        self.widget.configure(state='normal')
        self.widget.insert(tk.END, message + '\n', level_name)
        self.widget.see(tk.END)
        self.widget.configure(state='disabled')


class AppLogger:
    def __init__(self, name: str = 'rutube_app'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        self.logger.propagate = False

    def setup(self, log_file: Path | None = None, level: int = logging.INFO) -> logging.Logger:
        self.logger.setLevel(level)
        self.logger.handlers.clear()
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(message)s')

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        if log_file:
            file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        return self.logger

    def attach_gui(self, widget: tk.Text) -> None:
        for handler in list(self.logger.handlers):
            if isinstance(handler, TkTextHandler):
                self.logger.removeHandler(handler)
        widget.tag_config('DEBUG', foreground='cyan')
        widget.tag_config('INFO', foreground='black')
        widget.tag_config('WARNING', foreground='orange')
        widget.tag_config('ERROR', foreground='red')
        widget.tag_config('CRITICAL', foreground='red')
        self.logger.addHandler(TkTextHandler(widget))


logger = AppLogger()
