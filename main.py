#version=0.3

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


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# Логирование
LOG_FILE = "rutube_download.log"
logging.basicConfig(
    filename=LOG_FILE,
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

colorama_init()

class LoggerStream:
    def __init__(self, stream, log_func):
        self.stream = stream
        self.log_func = log_func
        self.ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')  # regex to remove ANSI

    def write(self, message):
        self.stream.write(message)
        self.stream.flush()
        clean = self.ansi_escape.sub('', message).strip()
        if clean:
            self.log_func(clean)

    def flush(self):
        self.stream.flush()

sys.stdout = LoggerStream(sys.stdout, logging.info)
sys.stderr = LoggerStream(sys.stderr, logging.error)



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

def download_video2(meta, folder, prefix):
    title = meta.get("title", "Без названия")
    url = meta.get("webpage_url")
    filename_mp4 = os.path.join(folder, f"{prefix}{sanitize_filename(title)}.mp4")

    if os.path.exists(filename_mp4):
        print(f"[✓] Уже загружено: {filename_mp4}")
        logging.info(f"Пропущено (уже есть): {title}")
        return

    try:
        ydl_opts = {
            "outtmpl": filename_mp4,
            "quiet": False,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        logging.info(f"Скачано видео: {title}")
    except Exception as e:
        print(f"[!] Ошибка при скачивании: {title} — {e}")
        logging.error(f"Ошибка скачивания: {title} — {e}")

def download_video(meta, folder, prefix):
    title = meta.get("title", "Без названия")
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


def save_metadata_csv(metadata_list, folder):
    csv_path = os.path.join(folder, "metadata.csv")
    if not metadata_list:
        return

    keys = set()
    for entry in metadata_list:
        keys.update(entry.keys())

    keys = sorted(keys)

    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=keys)
        writer.writeheader()
        for entry in metadata_list:
            writer.writerow(entry)

def main():
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
