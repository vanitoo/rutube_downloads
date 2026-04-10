from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from app.rutube_config import ConfigManager
from app.rutube_downloader import RutubeDownloader
from app.rutube_logger import logger as app_logger
from app.rutube_models import AppSettings, DownloadStatus, VideoMetadata
from app.rutube_storage import LocalStorage


class RutubeGUI:
    def __init__(self, downloader: RutubeDownloader, config_manager: ConfigManager, storage: LocalStorage):
        self.downloader = downloader
        self.config_manager = config_manager
        self.storage = storage
        self.settings = config_manager.load()
        self.current_videos: list[VideoMetadata] = []
        self.video_by_id: dict[str, VideoMetadata] = {}
        self.current_folder: Path | None = None
        self.sort_reverse_by_column: dict[str, bool] = {}
        self.window = tk.Tk()
        self.window.title('Rutube Downloader')
        self.window.geometry('1350x800')
        self._build_ui()
        self._restore_settings()

    def _build_ui(self) -> None:
        top = tk.Frame(self.window)
        progress = tk.Frame(self.window)
        table_frame = tk.Frame(self.window)
        log_frame = tk.Frame(self.window)
        top.pack(fill='x', pady=10)
        progress.pack(fill='x', padx=10, pady=(0, 10))
        table_frame.pack(fill='both', expand=True, padx=10, pady=5)
        log_frame.pack(fill='both', padx=10, pady=10)

        tk.Label(top, text='Ссылка на канал:').pack(side='left')
        self.url_entry = tk.Entry(top, width=50)
        self.url_entry.pack(side='left', padx=5)
        self.get_list_btn = tk.Button(top, text='📄 Получить список', command=self.on_get_list)
        self.get_list_btn.pack(side='left', padx=5)
        self.download_btn = tk.Button(top, text='⬇️ Скачать', state='disabled', command=self.on_download)
        self.download_btn.pack(side='left', padx=5)
        self.stop_btn = tk.Button(top, text='⏹ Остановить', command=self.on_cancel)
        self.stop_btn.pack(side='left', padx=5)
        self.settings_btn = tk.Button(top, text='⚙️ Настройки', command=self.open_settings_dialog)
        self.settings_btn.pack(side='left', padx=5)
        tk.Label(top, text='Папка загрузки:').pack(side='left', padx=(20, 5))
        self.path_var = tk.StringVar()
        tk.Entry(top, textvariable=self.path_var, width=30).pack(side='left', padx=5)
        tk.Button(top, text='📁', command=self.choose_folder).pack(side='left', padx=3)
        self.select_all_var = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text='Выбрать все', variable=self.select_all_var, command=self.toggle_all).pack(side='left', padx=(10, 0))

        self.progress_var = tk.IntVar(value=0)
        ttk.Progressbar(progress, variable=self.progress_var, maximum=100).pack(fill='x', pady=5)
        self.progress_label = tk.Label(progress, text='Готов к работе', anchor='w')
        self.progress_label.pack(fill='x')

        columns = ('#', 'Название', 'Дата', 'Время', 'Длительность', 'Статус', '✓')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings')
        for col in columns:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c))
        self.tree.column('#', width=40, anchor='center')
        self.tree.column('Название', width=500, anchor='w')
        self.tree.column('Дата', width=100, anchor='center')
        self.tree.column('Время', width=80, anchor='center')
        self.tree.column('Длительность', width=100, anchor='center')
        self.tree.column('Статус', width=120, anchor='center')
        self.tree.column('✓', width=20, anchor='center')
        vsb = ttk.Scrollbar(table_frame, orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.log_console = scrolledtext.ScrolledText(log_frame, height=10, wrap='word', state='disabled')
        self.log_console.pack(fill='both', expand=True)
        app_logger.attach_gui(self.log_console)

        self.tree.bind('<Button-1>', self._on_tree_click)
        self.tree.bind('<Double-1>', self._on_tree_double_click)
        self.window.protocol('WM_DELETE_WINDOW', self.on_close)

    def _restore_settings(self) -> None:
        self.url_entry.insert(0, self.settings.last_url)
        self.path_var.set(str(self.settings.download_folder))

    def current_settings(self) -> AppSettings:
        return AppSettings(
            download_folder=Path(self.path_var.get() or 'rutube_downloads'),
            concurrent_fragment_count=self.settings.concurrent_fragment_count,
            max_parallel_downloads=self.settings.max_parallel_downloads,
            last_url=self.url_entry.get().strip(),
        ).normalized()

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.path_var.get() or '.')
        if folder:
            self.path_var.set(folder)

    def toggle_all(self) -> None:
        value = '✓' if self.select_all_var.get() else ''
        for iid in self.tree.get_children():
            values = list(self.tree.item(iid, 'values'))
            values[-1] = value
            self.tree.item(iid, values=values)

    def _on_tree_click(self, event) -> None:
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if col == '#7' and item:
            values = list(self.tree.item(item, 'values'))
            values[-1] = '✓' if values[-1] != '✓' else ''
            self.tree.item(item, values=values)

    def _on_tree_double_click(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if not item or self.current_folder is None:
            return
        video = self.video_by_id.get(item)
        if not video:
            return
        file_path = self.current_folder / video.mp4_filename
        if not file_path.exists():
            app_logger.logger.warning('Файл ещё не скачан: %s', file_path.name)
            return
        try:
            self.storage.open_file(file_path)
            app_logger.logger.info('Открываю файл: %s', file_path.name)
        except Exception as exc:
            app_logger.logger.exception('Не удалось открыть файл %s: %s', file_path, exc)
            messagebox.showerror('Ошибка', f'Не удалось открыть файл:\n{file_path}')

    def on_get_list(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror('Ошибка', 'Введите ссылку')
            return
        if 'rutube.ru' not in url:
            messagebox.showerror('Ошибка', 'Некорректная ссылка')
            return
        self._clear_table()
        self.current_videos = []
        self.video_by_id = {}
        self.current_folder = None
        self.progress_var.set(0)
        self.progress_label.config(text='Получаю список видео...')
        self.download_btn.config(state='disabled')
        self._set_busy(True)

        def worker() -> None:
            try:
                settings = self.current_settings()
                channel, folder, videos = self.downloader.get_channel_videos(
                    url,
                    settings,
                    progress_callback=lambda message: self.window.after(0, lambda m=message: self.progress_label.config(text=m)),
                )
                self.window.after(0, lambda: self._populate_table(videos, folder))
                self.window.after(0, lambda: self.progress_label.config(text=f'Список видео загружен: {len(videos)}'))
            except Exception as exc:
                self.window.after(0, lambda: messagebox.showerror('Ошибка', str(exc)))
                app_logger.logger.exception('Ошибка получения списка: %s', exc)
            finally:
                self.window.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_table(self, videos: list[VideoMetadata], folder: Path) -> None:
        self.current_videos = videos
        self.current_folder = folder
        self.video_by_id = {video.video_id: video for video in videos}
        for index, video in enumerate(videos, start=1):
            status = DownloadStatus.SKIPPED.value if self.storage.video_exists(folder, video) else DownloadStatus.PENDING.value
            self.tree.insert('', 'end', iid=video.video_id, values=(
                index,
                video.title,
                video.formatted_date,
                '00:00',
                video.formatted_duration,
                status,
                '✓',
            ))
        self.download_btn.config(state='normal' if videos else 'disabled')

    def _clear_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def on_download(self) -> None:
        if self.current_folder is None:
            messagebox.showerror('Ошибка', 'Сначала получите список видео')
            return
        selected_ids = [iid for iid in self.tree.get_children() if self.tree.item(iid, 'values')[-1] == '✓']
        selected_videos = [self.video_by_id[iid] for iid in selected_ids if iid in self.video_by_id]
        if not selected_videos:
            messagebox.showwarning('Предупреждение', 'Нет выбранных видео')
            return
        self.progress_var.set(0)
        self.progress_label.config(text='Загрузка запущена...')
        self._set_busy(True)

        def status_callback(index: int, status: DownloadStatus, percent: int, _message: str | None) -> None:
            self.window.after(0, lambda: self._update_row_status(index, selected_ids, status, percent, len(selected_videos)))

        def progress_callback(index: int, data: dict, total: int) -> None:
            self.window.after(0, lambda: self._update_download_progress(index, selected_ids, data, total))

        def worker() -> None:
            try:
                self.downloader.download_videos(selected_videos, self.current_folder, self.current_settings(), status_callback, progress_callback)
                self.window.after(0, lambda: self.progress_label.config(text='Загрузка завершена'))
            except Exception as exc:
                app_logger.logger.exception('Ошибка загрузки: %s', exc)
                self.window.after(0, lambda: messagebox.showerror('Ошибка', str(exc)))
            finally:
                self.window.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _update_row_status(self, index: int, selected_ids: list[str], status: DownloadStatus, percent: int, total: int) -> None:
        if index >= len(selected_ids):
            return
        iid = selected_ids[index]
        if iid not in self.tree.get_children():
            return
        values = list(self.tree.item(iid, 'values'))
        values[-2] = status.value
        self.tree.item(iid, values=values)
        self.tree.selection_set(iid)
        self.tree.see(iid)
        done = sum(1 for row_id in selected_ids if row_id in self.tree.get_children() and self.tree.item(row_id, 'values')[-2] in {DownloadStatus.COMPLETED.value, DownloadStatus.SKIPPED.value})
        overall_percent = int((done / total) * 100) if total else percent
        if status in {DownloadStatus.COMPLETED, DownloadStatus.SKIPPED}:
            self.progress_var.set(overall_percent)
            self.progress_label.config(text=f'Загружено файлов: {done}/{total}')
        elif status == DownloadStatus.DOWNLOADING:
            self.progress_label.config(text='Загрузка запущена...')

    def _update_download_progress(self, index: int, selected_ids: list[str], data: dict, total: int) -> None:
        if index >= len(selected_ids):
            return
        iid = selected_ids[index]
        if iid not in self.tree.get_children():
            return
        values = list(self.tree.item(iid, 'values'))
        status = data.get('status')
        if status == 'downloading':
            fragment_index = data.get('fragment_index')
            fragment_count = data.get('fragment_count')
            downloaded = data.get('downloaded_bytes') or 0
            total_bytes = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            percent = int(downloaded * 100 / total_bytes) if total_bytes else None
            if fragment_index and fragment_count:
                label = f'Видео {index + 1}/{total}: фрагмент {fragment_index}/{fragment_count}'
                row_status = f'⬇️ {fragment_index}/{fragment_count}'
            elif percent is not None:
                label = f'Видео {index + 1}/{total}: {percent}%'
                row_status = f'⬇️ {percent}%'
            else:
                label = f'Видео {index + 1}/{total}: загрузка...'
                row_status = DownloadStatus.DOWNLOADING.value
            values[-2] = row_status
            self.tree.item(iid, values=values)
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self.progress_label.config(text=label)
        elif status == 'finished':
            self.progress_label.config(text=f'Видео {index + 1}/{total}: файл собран, постобработка...')

    def _sort_by_column(self, column: str) -> None:
        items = list(self.tree.get_children())
        reverse = self.sort_reverse_by_column.get(column, False)
        col_index = {'#': 0, 'Название': 1, 'Дата': 2, 'Время': 3, 'Длительность': 4, 'Статус': 5, '✓': 6}[column]

        def key_func(iid: str):
            value = self.tree.item(iid, 'values')[col_index]
            if column == '#':
                try:
                    return int(value)
                except Exception:
                    return 0
            return str(value).lower()

        items.sort(key=key_func, reverse=reverse)
        for position, iid in enumerate(items):
            self.tree.move(iid, '', position)
        self.sort_reverse_by_column[column] = not reverse

    def on_cancel(self) -> None:
        self.downloader.cancel_download()
        app_logger.logger.warning('Запрошена отмена загрузки')
        self.progress_label.config(text='Отмена загрузки...')

    def open_settings_dialog(self) -> None:
        dialog = tk.Toplevel(self.window)
        dialog.title('Настройки загрузки')
        dialog.geometry('320x150')
        dialog.resizable(False, False)
        tk.Label(dialog, text='Потоков скачивания:').grid(row=0, column=0, padx=10, pady=10, sticky='w')
        concurrent_var = tk.IntVar(value=self.settings.concurrent_fragment_count)
        tk.Spinbox(dialog, from_=1, to=10, textvariable=concurrent_var).grid(row=0, column=1, padx=10, pady=10)
        tk.Label(dialog, text='Параллельно файлов:').grid(row=1, column=0, padx=10, pady=10, sticky='w')
        workers_var = tk.IntVar(value=self.settings.max_parallel_downloads)
        tk.Spinbox(dialog, from_=1, to=10, textvariable=workers_var).grid(row=1, column=1, padx=10, pady=10)
        tk.Button(dialog, text='Сохранить', command=lambda: self.save_settings(dialog, concurrent_var.get(), workers_var.get())).grid(row=2, column=0, padx=10, pady=10)
        tk.Button(dialog, text='Отмена', command=dialog.destroy).grid(row=2, column=1, padx=10, pady=10)

    def save_settings(self, dialog: tk.Toplevel, concurrent: int, workers: int) -> None:
        self.settings = AppSettings(
            download_folder=Path(self.path_var.get() or 'rutube_downloads'),
            concurrent_fragment_count=concurrent,
            max_parallel_downloads=workers,
            last_url=self.url_entry.get().strip(),
        ).normalized()
        self.config_manager.save(self.settings)
        dialog.destroy()

    def _set_busy(self, busy: bool) -> None:
        state = 'disabled' if busy else 'normal'
        self.get_list_btn.config(state=state)
        self.download_btn.config(state=state if self.tree.get_children() else 'disabled')
        self.settings_btn.config(state=state)

    def on_close(self) -> None:
        self.settings = AppSettings(
            download_folder=Path(self.path_var.get() or 'rutube_downloads'),
            concurrent_fragment_count=self.settings.concurrent_fragment_count,
            max_parallel_downloads=self.settings.max_parallel_downloads,
            last_url=self.url_entry.get().strip(),
        ).normalized()
        self.config_manager.save(self.settings)
        self.window.destroy()

    def run(self) -> None:
        self.window.mainloop()


def create_gui(downloader: RutubeDownloader, config_manager: ConfigManager, storage: LocalStorage) -> RutubeGUI:
    return RutubeGUI(downloader, config_manager, storage)
