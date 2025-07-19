import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Any, TextIO

import requests
import yt_dlp

from rutube_logger import logger

HEADERS = {"User-Agent": "Mozilla/5.0"}
CONFIG_FILE = "rutube_config.json"


class YTDLogger:
    def debug(self, msg):
        if msg.strip():
            logger.debug(msg)

    def info(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def get_video_links(channel_url):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.common.by import By
    except ImportError as e:
        logger.critical("Ошибка", f"Selenium не установлен: {e}")
        return

    if not channel_url.endswith("/videos/"):
        channel_url = channel_url.rstrip("/") + "/videos/"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(channel_url)
    logger.info("🔄 Загружаю страницу канала...")

    scroll_pause = 2  # Начальная задержка
    max_attempts = 50
    last_height = driver.execute_script("return document.body.scrollHeight")
    # for _ in range(max_attempts):
    #     driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    #     time.sleep(scroll_pause)
    #     new_height = driver.execute_script("return document.body.scrollHeight")
    #     if new_height == last_height:
    #         break
    #     last_height = new_height
    for attempt in range(max_attempts):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        logger.info(f"Скролл {attempt + 1}/{max_attempts}...")
        time.sleep(scroll_pause)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            logger.info("Достигнут конец страницы.")
            break
        last_height = new_height
        logger.debug(f"Скролл {attempt + 1}/{max_attempts} | Пауза: {scroll_pause:.1f} сек | Высота: {new_height}px")
        # if new_height == last_height and attempt > 5:  # Если 5 скроллов подряд без изменений
        #     break

    try:
        raw_title = driver.find_element(By.XPATH, "//meta[@property='og:title']").get_attribute("content")
        title = raw_title.split("—")[0].strip()
    except:
        title = "Unnamed_Channel"

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
        logger.error(f"Ошибка получения мета-данных: {video_url} — {e}")
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
        logger.error(f"Ошибка сохранения обложки: {title} — {e}")


def download_video(meta, folder, prefix):
    title = meta.get("title", "Без названия")
    title = re.sub(r'\.(mp4|mkv|avi|mov)$', '', title, flags=re.IGNORECASE)
    url = meta.get("webpage_url")
    filename_base = f"{prefix}{sanitize_filename(title)}.mp4"
    filename_mp4 = os.path.join(folder, filename_base)

    related_garbage = [
        f for f in os.listdir(folder)
        if f.startswith(filename_base) and (
                f.endswith(".part") or
                f.endswith(".ytdl") or
                ".part-" in f or
                f.split(".")[-2] == "temp"
        )
    ]

    if os.path.exists(filename_mp4):
        if related_garbage:
            logger.info(f"[!] Найдены фрагменты: {related_garbage} — удаляем и перекачиваем: {filename_mp4}")
            try:
                os.remove(filename_mp4)
                for g in related_garbage:
                    os.remove(os.path.join(folder, g))
            except Exception as e:
                logger.error(f"Ошибка при удалении временных файлов: {e}")
                return
        else:
            logger.warning(f"[✓] Уже загружено: {filename_mp4}")
            return
    elif related_garbage:
        logger.error(f"[!] Остатки от старой загрузки — удаляем: {related_garbage}")
        for g in related_garbage:
            try:
                os.remove(os.path.join(folder, g))
            except Exception as e:
                logger.error(f"Не удалось удалить мусорный файл: {g} — {e}")

    try:
        ydl_opts = {
            "outtmpl": os.path.join(folder, filename_base),
            "quiet": False,
            "no_warnings": True,
            "logger": YTDLogger()
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        logger.info(f"Скачано: {filename_mp4}")
    except Exception as e:
        logger.error(f"Ошибка загрузки: {title} — {e}")


# def save_metadata_csv(metadata_list, folder):
def save_metadata_csv(metadata_list: List[Dict[str, Any]], folder: str) -> None:
    csv_path = os.path.join(folder, "metadata.csv")
    if not metadata_list:
        return

    keys = sorted({k for d in metadata_list for k in d.keys()})

    file: TextIO
    with open(csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        writer.writerows(metadata_list)


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
            logger.error(f"[!] Не удалось извлечь мета-данные для {url}: {e}")

    if updated:
        save_metadata_json(new_metadata, cache_path)

    return list(new_metadata.values())


def load_config():
    try:
        if Path(CONFIG_FILE).exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации: {e}")
    return {"last_url": "", "download_folder": "rutube_downloads"}


def save_config(last_url, download_folder):
    try:
        config = {"last_url": last_url, "download_folder": download_folder}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения конфигурации: {e}")
