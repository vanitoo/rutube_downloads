import os
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

# from rutube_downloader import RutubeDownloader
from rutube_functions import sanitize_filename, load_config, save_config
from rutube_logger import logger


class RutubeGUI:
    def __init__(self, downloader):
        self.downloader = downloader
        self.window = tk.Tk()
        self.row_refs = []
        self.current_metas = []
        self.setup_ui()
        self.load_initial_config()

    def setup_ui(self):
        """Инициализация всех компонентов GUI"""
        self.window.title("Rutube Video Downloader")
        self.window.geometry("1200x800")

        # Основные фреймы
        self.top_frame = tk.Frame(self.window)
        self.progress_frame = tk.Frame(self.window)
        self.table_frame = tk.Frame(self.window)
        self.log_frame = tk.Frame(self.window)

        # Виджеты
        self._create_url_entry()
        self._create_buttons()
        self._create_progress_bar()
        self._create_table()
        self._create_log_console()

        # Размещение фреймов
        self.top_frame.pack(fill="x", pady=10)
        self.progress_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.table_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_frame.pack(fill="both", padx=10, pady=10)

        # Обработчики событий
        self._bind_events()

    def load_initial_config(self):
        """Загрузка конфигурации при старте"""
        config = load_config()
        if config:
            self.url_entry.insert(0, config.get("last_url", ""))
            self.path_var.set(config.get("download_folder", self.downloader.output_dir))
            self.downloader.output_dir = self.path_var.get()

    def save_current_config(self):
        """Сохранение текущей конфигурации"""
        save_config(
            last_url=self.url_entry.get().strip(),
            download_folder=self.path_var.get(),
            concurrent_fragment_count=self.downloader.concurrent_fragment_count,
            max_workers=self.downloader.max_workers
        )

    def _create_url_entry(self):
        """Поле ввода URL"""
        tk.Label(self.top_frame, text="Ссылка на канал:", bg="#f0f0f0").pack(side="left")
        self.url_entry = tk.Entry(self.top_frame, width=45)
        self.url_entry.pack(side="left", padx=5)

    def _create_buttons(self):
        """Создание всех кнопок и элементов управления"""
        # Кнопка "Получить список"
        self.get_list_btn = tk.Button(
            self.top_frame,
            text="📄 Получить список",
            bg="#e0e0ff",
            command=self._on_get_list
        )
        self.get_list_btn.pack(side="left", padx=5)

        # Кнопка "Скачать"
        self.download_btn = tk.Button(
            self.top_frame,
            text="⬇️ Скачать",
            bg="#c0ffc0",
            state="disabled",
            command=self._on_download
        )
        self.download_btn.pack(side="left", padx=5)

        # Кнопка "Остановить"
        self.stop_btn = tk.Button(
            self.top_frame,
            text="⏹ Остановить",
            bg="#ffc0c0",
            command=self.downloader.cancel_download
        )
        self.stop_btn.pack(side="left", padx=5)

        # Кнопка "Настройки"
        self.settings_btn = tk.Button(
            self.top_frame,
            text="⚙️ Настройки",
            bg="#e0e0e0",
            command=self._open_settings_dialog
        )
        self.settings_btn.pack(side="left", padx=5)

        # Поле для папки загрузки
        tk.Label(self.top_frame, text="Папка загрузки:").pack(side="left", padx=(20, 5))

        self.path_var = tk.StringVar(value=self.downloader.output_dir)
        self.path_entry = tk.Entry(self.top_frame, textvariable=self.path_var, width=30)
        self.path_entry.pack(side="left", padx=5)

        # Кнопка выбора папки
        self.choose_btn = tk.Button(
            self.top_frame,
            text="📁",
            command=self._on_choose_folder
        )
        self.choose_btn.pack(side="left", padx=3)

        # Чекбокс "Выбрать все"
        self.select_all_var = tk.BooleanVar(value=True)
        self.select_all_cb = tk.Checkbutton(
            self.top_frame,
            text="Выбрать все",
            variable=self.select_all_var,
            command=self._on_toggle_all
        )
        self.select_all_cb.pack(side="left", padx=(10, 0))

    def _create_progress_bar(self):
        """Прогресс-бар"""
        self.progress_var = tk.IntVar()
        ttk.Progressbar(self.progress_frame, variable=self.progress_var,
                        maximum=100).pack(fill="x", pady=5)
        self.progress_label = tk.Label(self.progress_frame, text="Готов к работе",
                                       anchor="w")
        self.progress_label.pack(fill="x")

    def _create_table(self):
        """Создание таблицы с видео"""
        columns = ("#", "Название", "Дата", "Время", "Длительность", "Статус", "✓")
        self.tree = ttk.Treeview(self.table_frame, columns=columns, show="headings")

        # Настройка заголовков
        for col in columns:
            self.tree.heading(col, text=col)

        # Настройка ширины колонок (как в оригинале)
        self.tree.column("#", width=40, anchor="center")
        self.tree.column("Название", width=500, anchor="w")
        self.tree.column("Дата", width=100, anchor="center")
        self.tree.column("Время", width=80, anchor="center")
        self.tree.column("Длительность", width=100, anchor="center")
        self.tree.column("Статус", width=100, anchor="center")
        self.tree.column("✓", width=20, anchor="center")

        # Прокрутка
        vsb = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Размещение
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.table_frame.grid_rowconfigure(0, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)

    def _create_log_console(self):
        """Консоль логов"""
        self.log_console = scrolledtext.ScrolledText(self.log_frame, height=10,
                                                     wrap="word", state="normal")
        self.log_console.pack(fill="both", expand=True)

    def _on_choose_folder(self):
        """Обработчик выбора папки"""
        folder = filedialog.askdirectory(initialdir=self.path_var.get())
        if folder:
            self.path_var.set(folder)
            self.downloader.output_dir = folder

    def _on_toggle_all(self):
        """Обработчик чекбокса 'Выбрать все'"""
        val = "✓" if self.select_all_var.get() else ""
        for iid in self.tree.get_children():
            values = list(self.tree.item(iid, "values"))
            values[-1] = val
            self.tree.item(iid, values=values)

    def _bind_events(self):
        """Привязка обработчиков событий"""
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_tree_click(self, event):
        """Обработчик клика по таблице"""
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)

        if col == "#7":  # Колонка с чекбоксом
            values = list(self.tree.item(item, "values"))
            values[-1] = "✓" if values[-1] != "✓" else ""
            self.tree.item(item, values=values)

    def _on_get_list(self):
        """Получение списка видео"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Ошибка", "Введите ссылку")
            return

        threading.Thread(target=self._fetch_videos, args=(url,), daemon=True).start()

    def _fetch_videos(self, url):
        """Загрузка списка видео с проверкой существующих файлов"""
        self._update_ui_state(loading=True)
        try:
            logger.info("🔄 Получаю список видео с Rutube...")
            links, channel = self.downloader.get_video_links(url)
            logger.info(f"✅ Найдено видео: {len(links)}")

            metas = self.downloader.fetch_all_metadata(links)

            logger.info("📊 Формирую таблицу...")
            self.current_metas = metas
            self._update_table(metas)
            self._check_existing_files(channel)  # Проверка существующих файлов

            # self.window.after(0, lambda: self._safe_update_table(metas, channel))

            logger.info("✅ Список загружен")

        except Exception as e:
            logger.error(f"❌ Ошибка: {str(e)}")
        finally:
            self._update_ui_state(loading=False)

    def _safe_update_table(self, metas, channel):
        """Потокобезопасное обновление таблицы"""
        try:
            logger.debug("Начало обновления таблицы...")
            self.current_metas = metas
            self._update_table(metas)
            self._check_existing_files(channel)
            logger.info("✅ Таблица успешно обновлена")
        except Exception as e:
            logger.error(f"Ошибка обновления таблицы: {e}")

    def _check_existing_files(self, channel):
        """Проверка существующих файлов и обновление статусов"""
        for item_id in self.tree.get_children():
            values = list(self.tree.item(item_id, "values"))
            index = int(values[0]) - 1
            if 0 <= index < len(self.current_metas):
                meta = self.current_metas[index]
                path = self._get_video_path(meta, channel)
                # Обновляем только статус (5-я колонка), сохраняя остальные данные
                new_values = values.copy()
                new_values[5] = "✅ Готово" if os.path.exists(path) else "⏳"
                self.tree.item(item_id, values=new_values)

    def _get_video_path(self, meta, channel):
        """Генерация пути к видеофайлу"""
        title = re.sub(r'\.(mp4|mkv|avi|mov)$', '', meta.get("title", ""), flags=re.IGNORECASE)
        date_raw = meta.get("upload_date", "00000000").replace(".", "")
        duration = meta.get("duration_string", "00:00").replace(":", "").zfill(4)
        prefix = f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_{duration}_"
        filename = f"{prefix}{sanitize_filename(title)}.mp4"
        return os.path.join(self.downloader.output_dir, channel, filename)

    def _update_table(self, metas):
        """Обновление таблицы"""
        self.tree.delete(*self.tree.get_children())
        self.row_refs = []

        for i, meta in enumerate(metas, 1):
            self._add_video_row(meta, i)

        if self.row_refs:
            self.tree.selection_set(self.row_refs[0])

    def _add_video_row(self, meta, index):
        """Добавление строки в таблицу с корректным распределением данных"""
        title = meta.get("title", "Без названия")
        date_raw = meta.get("upload_date", "00000000")
        duration = meta.get("duration_string", "0:00")

        # Форматирование даты (YYYY.MM.DD)
        formatted_date = (f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}"
                          if len(date_raw) == 8 else date_raw)

        # Форматирование времени (HH:MM из длительности)
        time_parts = duration.split(":")
        if len(time_parts) == 2:
            formatted_time = f"{time_parts[0].zfill(2)}:{time_parts[1].zfill(2)}"
        else:
            formatted_time = duration

        item_id = self.tree.insert("", "end", values=(
            index,  # Колонка #
            title,  # Колонка "Название"
            formatted_date,  # Колонка "Дата"
            formatted_time,  # Колонка "Время"
            "00:00",  # Колонка "Длительность"
            "⏳",  # Колонка "Статус"
            "✓"  # Колонка "✓"
        ))
        self.row_refs.append(item_id)
        self.tree.see(item_id)

    def _on_download(self):
        """Запуск скачивания"""
        selected = self._get_selected_videos()
        if not selected:
            messagebox.showinfo("Информация", "Нет выбранных видео")
            return

        threading.Thread(target=self._download_videos, args=(selected,), daemon=True).start()

    def _download_videos(self, videos):
        """Фоновое скачивание"""
        self._update_ui_state(downloading=True)
        self.downloader._cancel_flag = False  # Сброс флага отмены
        total = len(videos)

        def progress_callback(index, status):
            # # Вывод в обе системы
            current_num = index + 1

            # Обработка отмены
            if self.downloader._cancel_flag:
                status = "🛑 Отменено"

            # Формируем сообщение
            if status == "✅ Готово":
                logger.info(f"[{current_num}/{total}] Файл уже существует")
            else:
                logger.info(f"[{current_num}/{total}] {status}")

            logger.info(f"[{current_num} / {total}] {status}")

            # Обновляем интерфейс
            self._update_row_status(index, status)
            self._focus_row(index)
            self._update_progress(int(current_num / total * 100))

            # Прерывание при отмене
            if self.downloader._cancel_flag:
                raise KeyboardInterrupt("Загрузка отменена пользователем")

        try:
            logger.info("⏬ Начало загрузки видео...")
            self.downloader.set_status_callback(progress_callback)
            self.downloader.download_all(videos)
            logger.info(f"✅ Успешно загружено {total} видео")

        except KeyboardInterrupt:
            logger.error(f"🛑 Загрузка прервана пользователем")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки: {str(e)}")
        finally:
            self._update_ui_state(downloading=False)

    def _get_selected_videos(self):
        """Получение выбранных видео"""
        selected = []
        for i, item_id in enumerate(self.tree.get_children()):
            if self.tree.item(item_id, "values")[-1] == "✓":
                selected.append(self.current_metas[i])
        return selected

    def _update_row_status(self, row_index, status):
        """Обновление статуса строки"""
        if row_index < len(self.row_refs):
            item_id = self.row_refs[row_index]
            values = list(self.tree.item(item_id, "values"))
            values[-2] = status
            self.tree.item(item_id, values=values)

    def _focus_row(self, row_index):
        """Фокус на строке"""
        if row_index < len(self.row_refs):
            item_id = self.row_refs[row_index]
            self.tree.see(item_id)
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)

    def _update_ui_state(self, loading=False, downloading=False):
        """Обновление состояния интерфейса"""
        state = "disabled" if loading or downloading else "normal"
        self.get_list_btn.config(state=state)
        self.download_btn.config(state=state)
        self.settings_btn.config(state=state)
        self.window.update()

    def _update_progress(self, percent):
        """Обновление прогресс-бара"""
        self.progress_var.set(percent)
        self.progress_label.config(text=f"Выполнено: {percent}%")
        self.window.update_idletasks()

    def _open_settings_dialog(self):
        """Открытие диалога настроек"""
        dialog = tk.Toplevel(self.window)
        dialog.title("Настройки загрузки")
        dialog.geometry("300x150")
        dialog.resizable(False, False)

        # Поле для потоков скачивания
        tk.Label(dialog, text="Потоков скачивания:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.concurrent_var = tk.IntVar(value=self.downloader.concurrent_fragment_count)
        tk.Spinbox(dialog, from_=1, to=10, textvariable=self.concurrent_var).grid(row=0, column=1, padx=10, pady=10)

        # Поле для параллельно файлов
        tk.Label(dialog, text="Параллельно файлов:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.workers_var = tk.IntVar(value=self.downloader.max_workers)
        tk.Spinbox(dialog, from_=1, to=10, textvariable=self.workers_var).grid(row=1, column=1, padx=10, pady=10)

        # Кнопки
        btn_frame = tk.Frame(dialog)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(btn_frame, text="Сохранить", command=lambda: self._save_settings(dialog)).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side="left", padx=5)

    def _save_settings(self, dialog):
        """Сохранение настроек"""
        concurrent = self.concurrent_var.get()
        workers = self.workers_var.get()
        self.downloader.update_settings(concurrent, workers)
        dialog.destroy()

    def _on_close(self):
        """Обработчик закрытия окна"""
        # self.downloader.last_url = self.url_entry.get().strip()
        # self.downloader.output_dir = self.path_var.get()
        self.save_current_config()
        self.window.destroy()

    def run(self):
        """Запуск приложения"""
        self.window.mainloop()


def create_gui(downloader):
    """Точка входа для создания GUI"""
    app = RutubeGUI(downloader)

    # Только добавляем GUI обработчик к существующему логгеру
    logger.update_gui_handler(app.log_console)
    logger.info("Приложение запущено")

    # logger.debug("Отладочная информация")
    # logger.info("Информационное сообщение")
    # logger.warning("Предупреждение")
    # logger.error("Ошибка")
    # logger.critical("Критическая ошибка")

    app.run()
