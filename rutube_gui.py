import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from tkinter import filedialog
import tkinter.font as tkFont
import threading
import sys
import logging
import re
from core_functions import sanitize_filename
import os



# Инициализация логирования
logging.basicConfig(
    filename="rutube_gui.log",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

class LogRedirector:
    def __init__(self, log_func):
        self.log_func = log_func
        # шаблон прогресса вида "[download]  43.8% of ..."
        self.progress_re = re.compile(r"\[download\]\s+\d{1,3}\.\d% of")

    def write(self, message):
        if message.strip():
            self.log_func(message.strip())  # Всегда выводим в GUI
            # Только если это не прогресс — пишем в файл
            if not self.progress_re.search(message):
                logging.info(message.strip())
            # if self.progress_re.search(message):
            #     return  # пропускаем прогресс
            # self.log_func(message.strip())
            # logging.info(message.strip())

    def flush(self):
        pass

def create_gui(downloader):
    window = tk.Tk()
    window.title("Rutube Video Downloader")
    window.geometry("1200x750")
    gui = {}
    row_refs = []
    current_metas = []

    def log_message(msg):
        window.after(0, lambda: (
            gui["log_console"].insert(tk.END, msg + "\n"),
            gui["log_console"].see(tk.END)
        ))

    def log_error(msg):
        window.after(0, lambda: (
            gui["log_console"].insert(tk.END, "ERROR: " + msg + "\n", 'error'),
            gui["log_console"].tag_config('error', foreground='red'),
            gui["log_console"].see(tk.END)
        ))

    sys.stdout = LogRedirector(log_message)
    sys.stderr = LogRedirector(log_error)

    top = tk.Frame(window)
    top.pack(fill="x", pady=10)
    tk.Label(top, text="Ссылка на канал:", bg="#f0f0f0").pack(side="left")
    url_entry = tk.Entry(top, width=45)
    url_entry.pack(side="left", padx=5)

    get_list_btn = tk.Button(top, text="📄 Получить список", bg="#e0e0ff",
                             command=lambda: threading.Thread(target=run_list, args=(url_entry.get().strip(),),
                                                              daemon=True).start())
    get_list_btn.pack(side="left", padx=5)

    download_btn = tk.Button(top, text="⬇️ Скачать", bg="#c0ffc0")
    download_btn.pack(side="left", padx=5)

    stop_btn = tk.Button(top, text="⏹ Остановить", bg="#ffc0c0", command=lambda: downloader.cancel_download())
    stop_btn.pack(side="left", padx=5)

    tk.Label(top, text="Папка загрузки:").pack(side="left", padx=(20, 5))
    path_var = tk.StringVar(value=downloader.output_dir)
    path_entry = tk.Entry(top, textvariable=path_var, width=30)
    path_entry.pack(side="left", padx=5)

    def choose_folder():
        folder = filedialog.askdirectory(initialdir=path_var.get())
        if folder:
            path_var.set(folder)
            downloader.output_dir = folder  # Обновляем папку в downloader

    choose_btn = tk.Button(top, text="📁", command=choose_folder)
    choose_btn.pack(side="left", padx=3)

    select_all_var = tk.BooleanVar(value=True)

    def toggle_all_checkboxes():
        val = "✓" if select_all_var.get() else ""
        for iid in tree.get_children():
            values = list(tree.item(iid, "values"))
            values[-1] = val
            tree.item(iid, values=values)

    select_all_cb = tk.Checkbutton(top, text="Выбрать все", variable=select_all_var, command=toggle_all_checkboxes)
    select_all_cb.pack(side="left", padx=(10, 0))

    progress_var = tk.IntVar()

    progress_frame = tk.Frame(window)
    progress_frame.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Progressbar(progress_frame, variable=progress_var, maximum=100).pack(fill="x", pady=5)
    progress_label = tk.Label(progress_frame, text="Готов к работе", anchor="w")
    progress_label.pack(fill="x")

    table_frame = tk.Frame(window)
    table_frame.pack(fill="both", expand=True, padx=10, pady=5)

    columns = ("#", "Название", "Дата", "Время", "Длительность", "Статус", "✓")
    tree = ttk.Treeview(table_frame, columns=columns, show="headings")

    for col in columns:
        tree.heading(col, text=col)

    tree.column("#", width=40, anchor="center")
    tree.column("Название", width=500, anchor="w")  # оставить широкий
    tree.column("Дата", width=100, anchor="center")
    tree.column("Время", width=80, anchor="center")
    tree.column("Длительность", width=100, anchor="center")
    tree.column("Статус", width=100, anchor="center")
    tree.column("✓", width=20, anchor="center")

    vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    table_frame.grid_rowconfigure(0, weight=1)
    table_frame.grid_columnconfigure(0, weight=1)

    def toggle_checkbox(event):
        item_id = tree.identify_row(event.y)
        col = tree.identify_column(event.x)
        if col == f"#{len(columns)}":  # последняя колонка — галочка
            values = list(tree.item(item_id, "values"))
            values[-1] = "✓" if values[-1] != "✓" else ""
            tree.item(item_id, values=values)

    tree.bind("<Button-1>", toggle_checkbox)

    def update_row_status(row_index, new_status):
        if row_index < len(row_refs):
            item_id = row_refs[row_index]
            values = tree.item(item_id, "values")
            values = list(values)
            values[-2] = new_status
            tree.item(item_id, values=values)

    def auto_resize_columns():
        f = tkFont.Font()
        for col in columns:
            max_width = f.measure(col)
            for iid in tree.get_children():
                val = str(tree.set(iid, col))
                max_width = max(max_width, f.measure(val))
            tree.column(col, width=max_width + 20)

    def add_video_to_table(meta, index):
        title = meta.get("title", "Без названия")
        date = meta.get("upload_date", "00000000")
        duration_raw = meta.get("duration_string", "0:00")
        duration_clean = duration_raw.replace(":", "").zfill(4)  # 7:5 → 0705
        time_str = f"{duration_clean[:2]}:{duration_clean[2:]}"  # 0705 → 07:05
        formatted = f"{date[:4]}.{date[4:6]}.{date[6:8]}" if len(date) == 8 else date
        # item_id = tree.insert("", "end", values=(index, title, formatted, time_str, duration_raw, "⏳"))
        item_id = tree.insert("", "end", values=(index, title, formatted, time_str, duration_raw, "⏳", "✓"))
        row_refs.append(item_id)
        tree.see(item_id)

    def update_progress(message, value):
        progress_label.config(text=message)
        progress_var.set(value)

    def check_files_and_update_status(metas, channel):
        import os
        for item_id in tree.get_children():
            values = list(tree.item(item_id, "values"))
            index = int(values[0]) - 1
            if 0 <= index < len(metas):
                meta = metas[index]
                title = meta.get("title", "Без названия")
                title = re.sub(r'\.(mp4|mkv|avi|mov)$', '', title, flags=re.IGNORECASE)  # Удаляем расширение
                date_raw = values[2].replace(".", "")
                duration_raw = values[4].replace(":", "").zfill(4)
                prefix = f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_{duration_raw}_"
                filename = f"{prefix}{sanitize_filename(title)}.mp4"
                path = os.path.join(downloader.output_dir, channel, filename)

                status = "✅ Готово" if os.path.exists(path) else "⏳"
                values[-2] = status
                tree.item(item_id, values=values)

    def run_list(url):
        if not url:
            messagebox.showerror("Ошибка", "Введите ссылку")
            return

        # Очистка таблицы
        for iid in tree.get_children():
            tree.delete(iid)
        row_refs.clear()

        # Очистка лога
        gui["log_console"].delete('1.0', tk.END)

        download_btn.config(state="disabled")
        update_progress("Получаем список...", 0)
        try:
            links, channel = downloader.get_video_links(url)
            log_message(f"Найдено: {len(links)} видео")

            metas = downloader.fetch_all_metadata(links)
            total = len(metas)

            # Очистка таблицы и переменных
            for iid in tree.get_children():
                tree.delete(iid)
            row_refs.clear()

            for i, meta in enumerate(metas, 1):
                update_progress(f"Добавление {i}/{total}", int(i / total * 100))
                add_video_to_table(meta, i)

            if row_refs:
                tree.see(row_refs[0])
                tree.selection_set(row_refs[0])

            # Сохраняем метаданные глобально
            current_metas.clear()
            current_metas.extend(metas)

            # Проверка файлов и обновление статусов
            check_files_and_update_status(current_metas, channel)

            update_progress("Список загружен", 100)
        except Exception as e:
            log_error(str(e))
        finally:
            download_btn.config(state="normal")

    def run_list2(url):
        if not url:
            messagebox.showerror("Ошибка", "Введите ссылку")
            return
        download_btn.config(state="disabled")
        update_progress("Получаем список...", 0)
        try:
            links, channel = downloader.get_video_links(url)
            log_message(f"Найдено: {len(links)} видео")

            metas = downloader.fetch_all_metadata(links)
            total = len(metas)

            for i, meta in enumerate(metas, 1):
                update_progress(f"Добавление {i}/{total}", int(i / total * 100))
                add_video_to_table(meta, i)

            if row_refs:
                tree.see(row_refs[0])
                tree.selection_set(row_refs[0])

            # Проверка наличия уже скачанных файлов
            # for i, meta in enumerate(metas):
            #     title = meta.get("title", "Без названия")
            #     date_raw = meta.get("upload_date", "00000000")
            #     duration = meta.get("duration_string", "00:00").replace(":", "").zfill(4)
            #
            #     prefix = f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_{duration}_"
            #     filename = f"{prefix}{sanitize_filename(title)}.mp4"
            #     path = os.path.join(downloader.output_dir, channel, filename)
            #
            #     status = "✅ Готово" if os.path.exists(path) else "⏳"
            #     update_row_status(i, status)
            # Проверка наличия уже скачанных файлов для каждой строки в таблице
            for item_id in tree.get_children():
                values = list(tree.item(item_id, "values"))
                index_str, title, date_str, time_str, duration_raw, _, _ = values

                # Восстановление данных
                title = title or "Без названия"
                title = re.sub(r'\.(mp4|mkv|avi|mov)$', '', title, flags=re.IGNORECASE)  # Удаляем расширение
                date_raw = date_str.replace(".", "")
                duration = duration_raw.replace(":", "").zfill(4)
                prefix = f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_{duration}_"
                filename = f"{prefix}{sanitize_filename(title)}.mp4"
                path = os.path.join(downloader.output_dir, channel, filename)

                if os.path.exists(path):
                    status = "✅ Готово"
                    log_message(f"[Проверка] Файл найден: {path}")
                else:
                    status = "⏳"
                    log_message(f"[Проверка] НЕ найден: {path}")

                # Проверка
                status = "✅ Готово" if os.path.exists(path) else "⏳"

                # Обновляем именно этот item, не по индексу
                values[-2] = status  # колонка "Статус"
                tree.item(item_id, values=values)

            update_progress("Список загружен", 100)
        except Exception as e:
            log_error(str(e))
        finally:
            download_btn.config(state="normal")

    def run_download():
        download_btn.config(state="disabled")
        try:
            if not current_metas:
                messagebox.showwarning("Внимание", "Сначала получите список видео.")
                return

            # Собираем отмеченные видео
            selected_metas = []
            for item_id in tree.get_children():
                values = tree.item(item_id, "values")
                if values[-1] == "✓":  # чекбокс выбран
                    index = int(values[0]) - 1
                    if 0 <= index < len(current_metas):
                        selected_metas.append(current_metas[index])

            if not selected_metas:
                messagebox.showinfo("Информация", "Нет выбранных видео для скачивания.")
                return

            # Скачиваем выбранные видео
            total = len(selected_metas)
            progress_step = 100 / max(total, 1)
            current_progress = 0

            def progress_hook(idx, status_text):
                nonlocal current_progress
                update_row_status(idx, status_text)
                current_progress += progress_step
                update_progress(f"Загрузка {idx + 1}/{total}", int(current_progress))

            downloader.set_status_callback(progress_hook)
            downloader.download_all(selected_metas)

            update_progress("Готово", 100)
        except Exception as e:
            log_error(str(e))
        finally:
            download_btn.config(state="normal")

    def run_download2(url):
        update_progress("Загрузка ссылок...", 0)
        log_message(f"Загрузка ссылок...")

        download_btn.config(state="disabled")

        try:
            links, channel = downloader.get_video_links(url)
            log_message(f"Найдено: {len(links)} видео")

            metas = downloader.fetch_all_metadata(links)
            total = len(metas)

            # === ЭТАП 1: заполнение таблицы (50%) ===
            for i, meta in enumerate(metas, 1):
                percent = int(i / total * 50)
                update_progress(f"Добавление в таблицу {i}/{total}", percent)
                add_video_to_table(meta, i)

            update_progress("Сохранение метаданных...", 55)
            downloader.save_metadata(metas)

            # === ЭТАП 2: проверка и скачивание (80–100%) ===
            progress_step = 45 / max(len(metas), 1)  # 100–55 распределяем равномерно
            current_progress = 55

            def progress_hook(index, status_text):
                nonlocal current_progress
                update_row_status(index, status_text)
                current_progress += progress_step
                update_progress(f"Загрузка {index + 1}/{total}", int(current_progress))

            # передаём временный callback в downloader
            downloader.set_status_callback(progress_hook)

            selected_metas = []
            for iid in tree.get_children():
                values = tree.item(iid, "values")
                if values[-1] == "✓":
                    idx = int(values[0]) - 1
                    if idx < len(metas):
                        selected_metas.append(metas[idx])
            if not selected_metas:
                log_message("Нет отмеченных видео для загрузки")
                update_progress("Пропущено", 100)
                return
            downloader.download_all(selected_metas)
            # downloader.download_all(metas)

            update_progress("Готово", 100)

            if row_refs:
                tree.see(row_refs[0])
                tree.selection_set(row_refs[0])

        except Exception as e:
            log_error(str(e))
        finally:
            download_btn.config(state="normal")

    def on_start():
        url = url_entry.get().strip()
        if not url:
            messagebox.showerror("Ошибка", "Введите ссылку")
            return
        # threading.Thread(target=run_download, args=(url,), daemon=True).start()
        threading.Thread(target=run_download, daemon=True).start()

    download_btn.config(command=on_start)
    downloader.set_status_callback(update_row_status)

    log_frame = tk.Frame(window)
    log_frame.pack(fill="both", padx=10, pady=10)
    log_console = scrolledtext.ScrolledText(log_frame, height=10, wrap="word", state="normal")
    log_console.pack(fill="both", expand=True)
    log_console.config(state="normal")  # позволяет выделение + Ctrl+C

    gui.update({
        "download_btn": download_btn,
        "progress_label": progress_label,
        "tree": tree,
        "log_console": log_console
    })

    window.mainloop()
