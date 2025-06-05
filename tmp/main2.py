import os
import re
import csv
import requests
import yt_dlp
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import time

import concurrent.futures


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()

def get_video_links2(channel_url):
    if not channel_url.endswith("/videos/"):
        channel_url = channel_url.rstrip("/") + "/videos/"

    resp = requests.get(channel_url, headers=HEADERS)
    if resp.status_code != 200:
        raise Exception("Ошибка загрузки страницы канала")

    soup = BeautifulSoup(resp.text, "html.parser")

    # Название канала, обрезаем по "—"
    try:
        raw_title = soup.find("meta", property="og:title")["content"]
        title = raw_title.split("—")[0].strip()
    except:
        title = "Unnamed_Channel"

    links = set()
    for a in soup.find_all("a", href=True):
        match = re.match(r"^/video/([a-z0-9]{32})/$", a['href'])
        if match:
            full_url = "https://rutube.ru" + a['href']
            links.add(full_url)

    return sorted(links), sanitize_filename(title)

def get_video_links(channel_url):
    if not channel_url.endswith("/videos/"):
        channel_url = channel_url.rstrip("/") + "/videos/"

    # Настройка headless браузера
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

    # Поиск ссылок
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
        print(f"[!] Не удалось извлечь метаинформацию: {video_url}")
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
        print(f"[!] Не удалось сохранить обложку: {e}")

def download_video(video_url, folder, prefix):
    try:
        ydl_opts = {
            "outtmpl": os.path.join(folder, f"{prefix}%(title)s.%(ext)s"),
            "quiet": False,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        print(f"[!] Ошибка при скачивании: {e}")

def save_metadata_csv(metadata_list, folder):
    csv_path = os.path.join(folder, "metadata.csv")
    if not metadata_list:
        return

    # Соберем все уникальные ключи
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
        print(f"[{i}/{len(links)}] Обработка: {link}")
        meta = fetch_metadata(link)
        if meta:
            metadata_list.append(meta)

    print(f"[+] Сохраняем metadata.csv...")
    save_metadata_csv(metadata_list, base_folder)

    confirm = input("Скачать видео, описания и обложки? (да/нет): ").strip().lower()
    if confirm != "да":
        print("Отмена.")
        return

    for meta in metadata_list:
        title = meta.get("title", "Без названия")
        desc = meta.get("description", "Описание отсутствует")
        thumb = meta.get("thumbnail")
        url = meta.get("webpage_url")
        date_raw = meta.get("upload_date", "00000000")
        try:
            prefix = f"{date_raw[:4]}.{date_raw[4:6]}.{date_raw[6:8]}_"
        except:
            prefix = ""

        save_description(title, desc, base_folder, prefix)
        save_thumbnail(title, thumb, base_folder, prefix)
        download_video(url, base_folder, prefix)

if __name__ == "__main__":
    main()
