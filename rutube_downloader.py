import os
import time
import json
import re
import requests
import concurrent.futures
from core_functions import (
    get_video_links, fetch_metadata, fetch_and_cache_metadata,
    save_metadata_csv, save_description, save_thumbnail,
    download_video, sanitize_filename
)

class RutubeDownloader:
    def __init__(self):
        self.output_dir = "rutube_downloads"
        self.last_folder = ""
        self._cancel_flag = False
        self._status_callback = None  # GUI callback

    def set_status_callback(self, callback):
        """Устанавливает callback для обновления GUI-таблицы"""
        self._status_callback = callback

    def cancel_download(self):
        """Флаг отмены загрузки"""
        self._cancel_flag = True

    def get_video_links(self, url):
        links, channel_name = get_video_links(url)
        base_folder = os.path.join(self.output_dir, channel_name)
        os.makedirs(base_folder, exist_ok=True)
        self.last_folder = base_folder
        return links, channel_name

    def fetch_metadata(self, link):
        return fetch_metadata(link)

    def fetch_all_metadata2(self, links):
        cache_path = os.path.join(self.last_folder, "metadata.json")
        return fetch_and_cache_metadata(links, cache_path)

    def fetch_all_metadata(self, links):
        cache_path = os.path.join(self.last_folder, "metadata.json")
        metadata_list = fetch_and_cache_metadata(links, cache_path)

        def sort_key(meta):
            date = meta.get("upload_date", "00000000")
            duration = meta.get("duration_string", "00:00")
            duration_numeric = int(duration.replace(":", "").zfill(4))
            return (date, duration_numeric)

        metadata_list.sort(key=sort_key)
        return metadata_list

    def save_metadata(self, metadata_list, folder=None):
        folder = folder or self.last_folder
        save_metadata_csv(metadata_list, folder)

    def process_video2(self, meta_with_index):
        index, total, meta = meta_with_index
        title = meta.get("title", "Без названия")
        desc = meta.get("description", "Описание отсутствует")
        thumb = meta.get("thumbnail")
        date_raw = meta.get("upload_date", "00000000")
        duration = meta.get("duration_string", "00:00").replace(":", "").zfill(4)

        # Префикс: дата_время_
        try:
            prefix = (
                f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_"
                f"{duration[:2]}{duration[2:4]}_"
            )
        except Exception:
            prefix = ""

        print(f"[{index}/{total}] Скачивается: {title}")
        save_description(title, desc, self.last_folder, prefix)
        save_thumbnail(title, thumb, self.last_folder, prefix)
        download_video(meta, self.last_folder, prefix)

    def process_video(self, meta_with_index):
        index, total, meta = meta_with_index
        title = meta.get("title", "Без названия")
        desc = meta.get("description", "Описание отсутствует")
        thumb = meta.get("thumbnail")
        date_raw = meta.get("upload_date", "00000000")
        duration = meta.get("duration_string", "00:00").replace(":", "").zfill(4)

        try:
            prefix = f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_{duration}_"
        except Exception:
            prefix = ""

        if self._cancel_flag:
            if self._status_callback:
                self._status_callback(index - 1, "🛑 Отменено")
            return

        print(f"[{index}/{total}] Скачивается: {title}")
        try:
            save_description(title, desc, self.last_folder, prefix)
            save_thumbnail(title, thumb, self.last_folder, prefix)
            download_video(meta, self.last_folder, prefix)
            if self._status_callback:
                self._status_callback(index - 1, "✅ Готово")
        except Exception as e:
            print(f"[!] Ошибка: {title} — {e}")
            if self._status_callback:
                self._status_callback(index - 1, "❌ Ошибка")

    def download_all2(self, metadata_list):
        indexed = [(i + 1, len(metadata_list), meta) for i, meta in enumerate(metadata_list)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.map(self.process_video, indexed)

    def download_all(self, metadata_list):
        self._cancel_flag = False  # сброс перед началом
        indexed = [(i + 1, len(metadata_list), meta) for i, meta in enumerate(metadata_list)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.map(self.process_video, indexed)
