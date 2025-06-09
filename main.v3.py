#Version=0.3

import os
import re
import csv
import sys
import time
import requests
import yt_dlp
import logging
import concurrent.futures
from tqdm import tqdm
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from colorama import init as colorama_init, Fore, Style
import os
import re
import csv
import sys
import time
import logging
import requests
import yt_dlp
import argparse
import concurrent.futures
from bs4 import BeautifulSoup
from datetime import datetime
from colorama import init as colorama_init, Fore, Style
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# from gui_interface import create_gui_interface, collect_video_status

import tkinter as tk
from tkinter import ttk, messagebox
import os
import os
import json
import yt_dlp


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

colorama_init()


# Логирование
logging.basicConfig(
    filename="rutube_download.log",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


class LoggerStream:
    def __init__(self, stream, log_func):
        self.stream = stream
        self.log_func = log_func
        self.ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')  # удаление ANSI escape
        # Регулярка для отсеивания строк прогресса загрузки
        self.skip_regex = re.compile(
            r'\[\s*download\s*\]\s+\d{1,3}\.\d% of ~?\s*[\d\.]+[KMGiB]+ at\s+[\d\.\sA-Za-z/]+ ETA .+',
            re.IGNORECASE
        )

    def write(self, message):
        self.stream.write(message)
        self.stream.flush()
        clean = self.ansi_escape.sub('', message).strip()

        # Пропускаем строки, которые совпадают с шаблоном прогресса загрузки
        if clean and not self.skip_regex.search(clean):
            self.log_func(clean)

    def flush(self):
        self.stream.flush()


sys.stdout = LoggerStream(sys.stdout, logging.info)
sys.stderr = LoggerStream(sys.stderr, logging.error)

LAST_FOLDER = ""

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()

def get_video_links(channel_url):
    if not channel_url.endswith("/videos/"):
        channel_url = channel_url.rstrip("/") + "/videos/"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(channel_url)

    # Прокрутка страницы
    scroll_pause = 2
    max_attempts = 50
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(max_attempts):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    # Название канала
    try:
        raw_title = driver.find_element(By.XPATH, "//meta[@property='og:title']").get_attribute("content")
        title = raw_title.split("—")[0].strip()
    except:
        title = "Unnamed_Channel"

    # Сбор ссылок
    elements = driver.find_elements(By.CSS_SELECTOR, "a[href^='/video/'][href$='/']")
    links = set()
    for el in elements:
        href = el.get_attribute("href")
        if href and re.match(r"^https://rutube\.ru/video/[a-z0-9]{32}/$", href):
            links.add(href)

    driver.quit()
    return sorted(links), sanitize_filename(title)

def fetch_metadata(video_url):
    try:
        ydl_opts = {'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(video_url, download=False)
    except Exception as e:
        logging.error(f"Ошибка получения мета-данных: {video_url} — {e}")
        return None

def save_description(title, description, folder, prefix):
    filename = os.path.join(folder, f"{prefix}{sanitize_filename(title)}.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(description)

def save_thumbnail(title, thumb_url, folder, prefix):
    if not thumb_url:
        return
    try:
        response = requests.get(thumb_url, headers=HEADERS)
        if response.status_code == 200:
            filename = os.path.join(folder, f"{prefix}{sanitize_filename(title)}.jpg")
            with open(filename, "wb") as f:
                f.write(response.content)
    except Exception as e:
        logging.error(f"Ошибка сохранения обложки: {title} — {e}")


def download_video(meta, folder, prefix):
    title = meta.get("title", "Без названия")
    title = re.sub(r'\.(mp4|mkv|avi|mov)$', '', title, flags=re.IGNORECASE)
    url = meta.get("webpage_url")
    filename_base = f"{prefix}{sanitize_filename(title)}.mp4"
    filename_mp4 = os.path.join(folder, filename_base)

    # Поиск связанных временных файлов
    related_garbage = []
    for f in os.listdir(folder):
        if f.startswith(filename_base) and (
            f.endswith(".part") or f.endswith(".ytdl") or ".part-" in f
        ):
            related_garbage.append(f)

    # Проверка существующего .mp4 и мусора
    if os.path.exists(filename_mp4):
        if related_garbage:
            print(f"[!] Найдены фрагменты: {related_garbage} — удаляем и перекачиваем: {filename_mp4}")
            logging.warning(f"Неполная загрузка: удаляем {filename_mp4} и {len(related_garbage)} врем. файлов")

            try:
                os.remove(filename_mp4)
                for g in related_garbage:
                    os.remove(os.path.join(folder, g))
            except Exception as e:
                logging.error(f"Ошибка при удалении временных файлов: {e}")
                return
        else:
            print(f"[✓] Уже загружено: {filename_mp4}")
            logging.info(f"Пропущено (чистый): {filename_mp4}")
            return
    elif related_garbage:
        print(f"[!] Остатки от старой загрузки без основного файла — удаляем: {related_garbage}")
        for g in related_garbage:
            try:
                os.remove(os.path.join(folder, g))
            except Exception as e:
                logging.error(f"Не удалось удалить мусорный файл: {g} — {e}")

    # Загрузка
    try:
        ydl_opts = {
            "outtmpl": os.path.join(folder, filename_base),
            "quiet": False,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        logging.info(f"Скачано: {filename_mp4}")
    except Exception as e:
        print(f"[!] Ошибка при скачивании: {title} — {e}")
        logging.error(f"Ошибка загрузки: {title} — {e}")

def download_video_test(meta, folder, prefix):
    title = meta.get("title", "Без названия")
    url = meta.get("webpage_url")
    filename_mp4 = os.path.join(folder, f"{prefix}{sanitize_filename(title)}.mp4")

    if os.path.exists(filename_mp4):
        part1 = filename_mp4 + ".part"
        part2 = filename_mp4 + ".ytdl"
        if os.path.exists(part1) or os.path.exists(part2):
            os.remove(part1) if os.path.exists(part1) else None
            os.remove(part2) if os.path.exists(part2) else None
            print(Fore.YELLOW + f"[!] Повторная загрузка из-за недокачки: {title}" + Style.RESET_ALL)
        else:
            print(Fore.GREEN + f"[✓] Уже загружено: {title}" + Style.RESET_ALL)
            return

    try:
        ydl_opts = {
            "outtmpl": filename_mp4,
            "quiet": False,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"[!] Ошибка при скачивании: {title} — {e}")


def save_metadata_csv(metadata_list, folder):
    csv_path = os.path.join(folder, "metadata.csv")
    if not metadata_list:
        return

    keys = set()
    for entry in metadata_list:
        keys.update(entry.keys())
    keys = sorted(keys)

    # keys = sorted({k for d in metadata_list for k in d.keys()})
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=keys)
        writer.writeheader()
        for entry in metadata_list:
            writer.writerow(entry)


def process_all(url):
    global LAST_FOLDER
    print("[*] Загружаем страницу канала...")
    try:
        links, channel_name = get_video_links(url)
    except Exception as e:
        print("Ошибка:", e)
        return

    if not links:
        print("Видео не найдены.")
        return

    base_folder = os.path.join("rutube_downloads", channel_name)
    os.makedirs(base_folder, exist_ok=True)
    LAST_FOLDER = base_folder

    print(f"[+] Канал: {channel_name}")
    print(f"[+] Найдено {len(links)} видео\n")

    # metadata_list = []
    # for i, link in enumerate(links, 1):
    #     print(f"[{i}/{len(links)}] Извлекаем мета-данные: {link}")
    #     meta = fetch_metadata(link)
    #     if meta:
    #         metadata_list.append(meta)

    cache_path = os.path.join(base_folder, "metadata.json")
    metadata_list = fetch_and_cache_metadata(links, cache_path)

    print(f"[+] Сохраняем metadata.csv...")
    save_metadata_csv(metadata_list, base_folder)

    print(Fore.YELLOW + "Скачивание начнётся через 3 сек..." + Style.RESET_ALL)
    time.sleep(3)

    def process_video(meta_with_index):
        index, total, meta = meta_with_index
        title = meta.get("title", "Без названия")
        desc = meta.get("description", "Описание отсутствует")
        thumb = meta.get("thumbnail")
        date_raw = meta.get("upload_date", "00000000")
        duration = meta.get("duration_string", "00:00").replace(":", "").zfill(4)

        try:
            # prefix = f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_"
           # Format: YYYY.MM.DD_HHMMSS_
            prefix = (
                f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_"
                f"{duration[:2]}{duration[2:4]}_"
                # f"{time_raw[:2]}{time_raw[2:4]}{time_raw[4:6]}_"
            )
        except:
            prefix = ""
        print(f"[{index}/{total}] Скачивается: {title}")
        save_description(title, desc, base_folder, prefix)
        save_thumbnail(title, thumb, base_folder, prefix)
        download_video(meta, base_folder, prefix)

    indexed_meta = [(i + 1, len(metadata_list), meta) for i, meta in enumerate(metadata_list)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.map(process_video, indexed_meta)

def cli_mode(url_arg=None):
    if url_arg:
        url = url_arg.strip()
    else:
        url = input("Введите ссылку на канал Rutube: ").strip()
    if not url:
        print("Ссылка пуста.")
        return
    process_all(url)


def root_callback(url):
    process_all(url)

def video_data_getter():
    return collect_video_status(LAST_FOLDER)





def create_gui_interface(root_callback, video_data_getter):
    def on_start():
        url = url_entry.get().strip()
        if not url:
            messagebox.showerror("Ошибка", "Введите ссылку на канал Rutube")
            return
        root_callback(url)

    def on_refresh():
        if not video_data_getter:
            return
        update_table(video_data_getter())

    def update_table(data):
        for row in tree.get_children():
            tree.delete(row)
        for i, video in enumerate(data, 1):
            tree.insert('', 'end', values=(
                i,
                video.get("filename", ""),
                video.get("filesize", ""),
                "✅" if video.get("jpg") else "",
                "✅" if video.get("txt") else "",
                video.get("date", "")
            ))

    window = tk.Tk()
    window.title("Rutube Video Downloader")
    window.geometry("1000x500")

    frame = tk.Frame(window)
    frame.pack(padx=10, pady=10, fill="x")

    tk.Label(frame, text="Ссылка на канал Rutube:").pack(side="left")
    url_entry = tk.Entry(frame, width=60)
    url_entry.pack(side="left", padx=5)
    start_btn = tk.Button(frame, text="Старт", command=on_start)
    start_btn.pack(side="left", padx=5)
    refresh_btn = tk.Button(frame, text="Обновить список", command=on_refresh)
    refresh_btn.pack(side="left")

    columns = ("#", "Файл", "Размер", "JPG", "TXT", "Дата")
    tree = ttk.Treeview(window, columns=columns, show='headings')
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="w", width=150 if col == "Файл" else 70)
    tree.pack(fill="both", expand=True, padx=10, pady=10)

    window.mainloop()


def load_cached_metadata(cache_path):
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_metadata_json(metadata_dict, cache_path):
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(metadata_dict, f, ensure_ascii=False, indent=2)

def fetch_and_cache_metadata(video_urls, cache_path):
    cached = load_cached_metadata(cache_path)
    new_metadata = {}
    updated = False

    for url in video_urls:
        video_id = url.rstrip('/').split('/')[-1]
        if video_id in cached:
            new_metadata[video_id] = cached[video_id]
            continue

        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                new_metadata[video_id] = info
                updated = True
        except Exception as e:
            print(f"[!] Не удалось извлечь мета-данные для {url}: {e}")

    if updated:
        save_metadata_json(new_metadata, cache_path)

    return list(new_metadata.values())



def main():
    # create_gui_interface(root_callback, video_data_getter)
    parser = argparse.ArgumentParser(description="Rutube Downloader")
    parser.add_argument("--cli", action="store_true", help="Запуск в режиме терминала")
    parser.add_argument("--url", type=str, help="Ссылка на канал Rutube")
    args = parser.parse_args()

    if args.cli:
        cli_mode(args.url)
    else:
        create_gui_interface(root_callback, video_data_getter)

    print("[*] Загрузка завершена...")
    exit()

    url = input("Введите ссылку на канал Rutube: ").strip()

    print("[*] Загружаем страницу канала...")
    try:
        links, channel_name = get_video_links(url)
    except Exception as e:
        print("Ошибка:", e)
        logging.error(f"Ошибка загрузки страницы: {e}")
        return

    if not links:
        print("Видео не найдены.")
        return

    base_folder = os.path.join("rutube_downloads", channel_name)
    os.makedirs(base_folder, exist_ok=True)

    print(f"[+] Канал: {channel_name}")
    print(f"[+] Найдено {len(links)} видео\n")

    metadata_list = []
    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}] Извлекаем мета-данные: {link}")
        meta = fetch_metadata(link)
        if meta:
            metadata_list.append(meta)

    print(f"[+] Сохраняем metadata.csv...")
    save_metadata_csv(metadata_list, base_folder)

    confirm = input(
        Fore.YELLOW + "Скачать видео, описания и обложки? (да/нет) [Да по умолчанию]: " + Style.RESET_ALL).strip().lower()
    if confirm not in ("", "да"):
        print(Fore.CYAN + "Отмена." + Style.RESET_ALL)
        return


    def process_video(meta_with_index):
        index, total, meta = meta_with_index
#    def process_video(meta):
        title = meta.get("title", "Без названия")
        print(f"[{index}/{total}] Скачивается: {title}")
        desc = meta.get("description", "Описание отсутствует")
        thumb = meta.get("thumbnail")
        date_raw = meta.get("upload_date", "00000000")
        try:
            prefix = f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_"
        except:
            prefix = ""

        filename_mp4 = os.path.join(base_folder, f"{prefix}{sanitize_filename(title)}.mp4")
        if os.path.exists(filename_mp4):
            print(f"[✓] Пропущено (уже есть): {title}")
            return

        save_description(title, desc, base_folder, prefix)
        save_thumbnail(title, thumb, base_folder, prefix)
        download_video(meta, base_folder, prefix)

    THREADS = 1
    print(f"[*] Запускаем загрузку в {THREADS} потока(ов)...")
    indexed_meta = [(i + 1, len(metadata_list), meta) for i, meta in enumerate(metadata_list)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
        list(tqdm(executor.map(process_video, indexed_meta), total=len(metadata_list), desc="Загрузка"))

#    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
#        list(tqdm(executor.map(process_video, metadata_list), total=len(metadata_list), desc="Загрузка"))

if __name__ == "__main__":
    main()
