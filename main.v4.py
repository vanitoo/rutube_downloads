# Version: 0.4 (Refactored)
import os
import re
import csv
import sys
import time
import json
import logging
import argparse
import concurrent.futures
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import requests
import yt_dlp
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from colorama import init as colorama_init, Fore, Style

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
from typing import List, Dict



# Constants
HEADERS = {"User-Agent": "Mozilla/5.0"}
DEFAULT_OUTPUT_DIR = "rutube_downloads"
MAX_WORKERS = 3
TEMP_EXTENSIONS = ('.part', '.ytdl', '.temp')
SUPPORTED_VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov')

# Initialize colorama
colorama_init()


class RutubeDownloader:
    def __init__(self, output_dir: str = DEFAULT_OUTPUT_DIR, max_workers: int = MAX_WORKERS):
        self.output_dir = output_dir
        self.max_workers = max_workers
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging system"""
        logging.basicConfig(
            filename="rutube_download.log",
            filemode="a",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
        sys.stdout = self.LoggerStream(sys.stdout, logging.info)
        sys.stderr = self.LoggerStream(sys.stderr, logging.error)

    class LoggerStream:
        """Custom stream to log output"""

        def __init__(self, stream, log_func):
            self.stream = stream
            self.log_func = log_func
            self.ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')

        def write(self, message):
            self.stream.write(message)
            self.stream.flush()
            clean = self.ansi_escape.sub('', message).strip()
            if clean:
                self.log_func(clean)

        def flush(self):
            self.stream.flush()

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Remove invalid characters from filename"""
        return re.sub(r'[\\/*?:"<>|]', "_", name).strip()

    def get_video_links(self, channel_url: str) -> Tuple[List[str], str]:
        """Extract all video links from channel"""
        if not channel_url.endswith("/videos/"):
            channel_url = channel_url.rstrip("/") + "/videos/"

        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        driver.get(channel_url)

        # Scroll to load all videos
        self._scroll_page(driver)

        try:
            raw_title = driver.find_element(
                By.XPATH, "//meta[@property='og:title']"
            ).get_attribute("content")
            title = raw_title.split("—")[0].strip()
        except Exception:
            title = "Unnamed_Channel"

        # Collect video links
        elements = driver.find_elements(
            By.CSS_SELECTOR, "a[href^='/video/'][href$='/']"
        )
        links = {
            el.get_attribute("href") for el in elements
            if el.get_attribute("href") and re.match(
                r"^https://rutube\.ru/video/[a-z0-9]{32}/$",
                el.get_attribute("href")
            )
        }

        driver.quit()
        return sorted(links), self.sanitize_filename(title)

    def _scroll_page(self, driver, max_attempts: int = 50):
        """Scroll page to load all content"""
        scroll_pause = 2
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(max_attempts):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def fetch_metadata(self, video_url: str) -> Optional[Dict]:
        """Get video metadata"""
        try:
            ydl_opts = {'quiet': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(video_url, download=False)
        except Exception as e:
            logging.error(f"Metadata error: {video_url} - {e}")
            return None

    def _clean_filename(self, title: str) -> str:
        """Remove video extensions from title"""
        title = re.sub(
            r'\.({})$'.format('|'.join(
                ext.replace('.', '') for ext in SUPPORTED_VIDEO_EXTENSIONS
            )),
            '', title, flags=re.IGNORECASE
        )
        return self.sanitize_filename(title)

    def download_video(self, meta: Dict, folder: str, prefix: str = "") -> bool:
        """Download single video"""
        title = meta.get("title", "Untitled")
        clean_title = self._clean_filename(title)
        url = meta.get("webpage_url")
        filename_base = f"{prefix}{clean_title}.mp4"
        filename_mp4 = os.path.join(folder, filename_base)

        # Clean up temp files
        self._remove_temp_files(folder, filename_base)

        if os.path.exists(filename_mp4):
            logging.info(f"Skipped (exists): {filename_mp4}")
            return False

        try:
            ydl_opts = {
                "outtmpl": filename_mp4,
                "quiet": False,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            logging.info(f"Downloaded: {filename_mp4}")
            return True
        except Exception as e:
            logging.error(f"Download failed: {title} - {e}")
            return False

    def _remove_temp_files(self, folder: str, filename_base: str):
        """Remove temporary download files"""
        for f in os.listdir(folder):
            full_path = os.path.join(folder, f)
            if (f.startswith(filename_base) and
                    any(f.endswith(ext) for ext in TEMP_EXTENSIONS)):
                try:
                    os.remove(full_path)
                except Exception as e:
                    logging.error(f"Failed to remove temp file {f}: {e}")

    def save_metadata(self, metadata_list: List[Dict], folder: str):
        """Save metadata to CSV and JSON"""
        if not metadata_list:
            return

        # Save CSV
        csv_path = os.path.join(folder, "metadata.csv")
        keys = sorted({k for d in metadata_list for k in d.keys()})
        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=keys)
            writer.writeheader()
            writer.writerows(metadata_list)

        # Save JSON
        json_path = os.path.join(folder, "metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata_list, f, ensure_ascii=False, indent=2)

    def process_channel(self, channel_url: str):
        """Main processing pipeline for a channel"""
        print("[*] Loading channel page...")
        try:
            links, channel_name = self.get_video_links(channel_url)
        except Exception as e:
            print(f"Error: {e}")
            return

        if not links:
            print("No videos found.")
            return

        base_folder = os.path.join(self.output_dir, channel_name)
        os.makedirs(base_folder, exist_ok=True)

        print(f"\n[+] Channel: {channel_name}")
        print(f"[+] Found {len(links)} videos\n")

        # Get metadata
        metadata_list = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_url = {
                executor.submit(self.fetch_metadata, link): link
                for link in links
            }
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    meta = future.result()
                    if meta:
                        metadata_list.append(meta)
                except Exception as e:
                    logging.error(f"Failed to get metadata for {url}: {e}")

        # Save metadata
        self.save_metadata(metadata_list, base_folder)

        # Download content
        print(Fore.YELLOW + "Download will start in 3 seconds..." + Style.RESET_ALL)
        time.sleep(3)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for meta in metadata_list:
                futures.append(executor.submit(self._process_single_video, meta, base_folder))

            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Video processing failed: {e}")

    def _process_single_video(self, meta: Dict, base_folder: str):
        """Process single video (download + save assets)"""
        title = meta.get("title", "Untitled")
        desc = meta.get("description", "No description")
        thumb = meta.get("thumbnail")

        # Create date prefix
        date_raw = meta.get("upload_date", "00000000")
        try:
            formatted_date = f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}"
        except:
            # prefix = ""
            formatted_date = "0000.00.00"

        duration = meta.get("duration_string", "00:00").replace(":", "")[:4]  # "7:14" -> "0714"
        time_part = f"{duration.ljust(4, '0')}"  # -> "0714"
        prefix = f"{formatted_date}_{time_part}_"  # -> "2025.01.21_0714_"

        print(f"Processing: {title}")

        # Save description
        desc_filename = os.path.join(base_folder, f"{prefix}{self._clean_filename(title)}.txt")
        with open(desc_filename, "w", encoding="utf-8") as f:
            f.write(desc)

        # Save thumbnail
        if thumb:
            thumb_filename = os.path.join(base_folder, f"{prefix}{self._clean_filename(title)}.jpg")
            try:
                response = requests.get(thumb, headers=HEADERS)
                if response.status_code == 200:
                    with open(thumb_filename, "wb") as f:
                        f.write(response.content)
            except Exception as e:
                logging.error(f"Thumbnail save failed: {title} - {e}")

        # Download video
        self.download_video(meta, base_folder, prefix)

class RutubeDownloaderGUI:
    def __init__(self, downloader):
        self.downloader = downloader
        self.window = tk.Tk()
        self.window.title("Rutube Video Downloader")
        self.window.geometry("1100x750")

        # Перенаправляем stdout/stderr в лог GUI
        sys.stdout = self.LogRedirector(self.log_message)
        sys.stderr = self.LogRedirector(self.log_error)

        self._setup_ui()
        self._bind_events()

    class LogRedirector:
        """Перенаправляет вывод консоли в лог GUI"""

        def __init__(self, log_func):
            self.log_func = log_func

        def write(self, message):
            if message.strip():
                self.log_func(message.strip())

        def flush(self):
            pass

    def _setup_ui(self):
        # Top controls frame
        top_frame = tk.Frame(self.window, bg="#f0f0f0")
        top_frame.pack(fill="x", pady=10)

        # URL input
        tk.Label(top_frame, text="Ссылка на канал:", bg="#f0f0f0").pack(side="left", padx=5)
        self.url_entry = tk.Entry(top_frame, width=50)
        self.url_entry.pack(side="left", padx=5)

        # Buttons
        self.download_btn = tk.Button(top_frame, text="⬇️ Скачать", command=self.start_download, bg="#c0ffc0")
        self.download_btn.pack(side="left", padx=5)

        self.check_btn = tk.Button(top_frame, text="🔍 Проверить", command=self.check_videos, bg="#e0e0e0")
        self.check_btn.pack(side="left", padx=5)

        # Progress bar
        progress_frame = tk.Frame(self.window, bg="#ffffff")
        progress_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=5)

        self.progress_label = tk.Label(progress_frame, text="Готов к работе", anchor="w", bg="#ffffff")
        self.progress_label.pack(fill="x")

        # Videos table
        table_frame = tk.Frame(self.window)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        columns = ("#", "Название", "Дата", "Длительность", "Статус")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")

        # Configure columns
        self.tree.column("#", width=40, anchor="center")
        self.tree.column("Название", width=400, anchor="w")
        self.tree.column("Дата", width=120, anchor="center")
        self.tree.column("Длительность", width=100, anchor="center")
        self.tree.column("Статус", width=120, anchor="center")

        for col in columns:
            self.tree.heading(col, text=col)

        # Scrollbars
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # Log console
        log_frame = tk.Frame(self.window)
        log_frame.pack(fill="both", expand=False, padx=10, pady=5)

        self.log_console = scrolledtext.ScrolledText(log_frame, height=10, wrap="word", state="normal")
        self.log_console.pack(fill="both", expand=True)

    def _bind_events(self):
        self.tree.bind("<Double-1>", self.on_video_double_click)

    def start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Ошибка", "Введите ссылку на канал Rutube")
            return

        threading.Thread(
            target=self._download_thread,
            args=(url,),
            daemon=True
        ).start()

    def _download_thread(self, url):
        self.update_progress("Начало загрузки...", 0)
        self.download_btn.config(state="disabled")

        try:
            self.log_message(f"Начинаем загрузку канала: {url}")

            # Process channel and update UI
            links, channel_name = self.downloader.get_video_links(url)
            self.log_message(f"Найдено видео: {len(links)}")

            metadata_list = []
            for i, link in enumerate(links, 1):
                self.log_message(f"Обработка видео {i}/{len(links)}", 10 + int(i / len(links) * 50))
                meta = self.downloader.fetch_metadata(link)
                if meta:
                    metadata_list.append(meta)
                self._add_video_to_table(meta, i)

                self.log_message("Сохранение метаданных...", 80)
                self.downloader.save_metadata(metadata_list, self.downloader.output_dir)

                self.log_message("Загрузка завершена!", 100)
        except Exception as e:
            self.log_error(f"Ошибка: {str(e)}")
        finally:
            self.download_btn.config(state="normal")

    def check_videos(self):
        """Check existing downloaded videos"""
        # Implement your checking logic here
        pass

    def on_video_double_click(self, event):
        item = self.tree.selection()[0]
        values = self.tree.item(item, "values")
        self.log_message(f"Выбрано видео: {values[1]}")

    def _add_video_to_table(self, meta: Dict, index: int):
        title = meta.get("title", "Без названия")
        date = meta.get("upload_date", "00000000")
        duration = meta.get("duration_string", "0:00")

        formatted_date = f"{date[:4]}.{date[4:6]}.{date[6:8]}" if len(date) == 8 else date

        self.tree.insert("", "end", values=(
            index,
            title,
            formatted_date,
            duration,
            "⏳ Ожидает"
        ))

    def update_progress(self, message: str, value: int):
        self.window.after(0, lambda:
        (self.progress_label.config(text=message),
         self.progress_var.set(value))
                          )

    # def log_message(self, message: str):
    #     self.window.after(0, lambda:
    #     self.log_console.insert("end", message + "\n")
    #                       )
    def log_message(self, message: str):
        """Вывод обычного сообщения в лог"""
        self.window.after(0, lambda:
            (self.log_console.insert(tk.END, message + "\n"),
            self.log_console.see(tk.END),
            self.log_console.update_idletasks()
             ))



    # def log_error(self, message: str):
    #     self.window.after(0, lambda:
    #     (self.log_console.insert("end", "ОШИБКА: " + message + "\n"),
    #      messagebox.showerror("Ошибка", message))

    def log_error(self, message: str):
        """Вывод ошибки в лог"""
        self.window.after(0, lambda:
        (self.log_console.insert(tk.END, f"ERROR: {message}\n", 'error'),
         self.log_console.tag_config('error', foreground='red'),
         self.log_console.see(tk.END),
         self.log_console.update_idletasks()
         )
                              )

    def run(self):
        self.window.mainloop()


import os
import argparse


def main():
    parser = argparse.ArgumentParser(description="Rutube Video Downloader")
    parser.add_argument("--cli", action="store_true", help="Launch in CLI mode")
    parser.add_argument("--url", type=str, help="Rutube channel URL (for CLI mode)")
    parser.add_argument("--output", type=str, default="downloads",
                        help="Output directory (default: 'downloads')")
    parser.add_argument("--threads", type=int, default=3,
                        help="Number of download threads (default: 3)")

    args = parser.parse_args()

    # Проверка доступности GUI в Linux/Unix без DISPLAY
    if not args.cli and os.name == 'posix' and 'DISPLAY' not in os.environ:
        print("Ошибка: GUI недоступен в этом терминале.")
        print("Используйте:")
        print("  python main.py --cli --url <ссылка>")
        print("или экспортируйте DISPLAY для графического режима")
        return

    # Инициализация загрузчика с параметрами
    downloader = RutubeDownloader(
        output_dir=args.output,
        max_workers=args.threads
    )

    if args.cli:
        # Консольный режим
        if args.url:
            url = args.url.strip()
        else:
            url = input("Введите ссылку на канал Rutube: ").strip()

        if not url:
            print("Ошибка: не указана ссылка на канал")
            return

        print(f"\nЗагрузка канала в папку: {args.output}")
        print(f"Количество потоков: {args.threads}\n")
        downloader.process_channel(url)
    else:
        # Графический интерфейс (по умолчанию)
        gui = RutubeDownloaderGUI(downloader)
        gui.run()

if __name__ == "__main__":
    main()