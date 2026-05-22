from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Callable

from requests import options
import yt_dlp
#from yt_dlp import options

from app.rutube_models import ChannelInfo, VideoMetadata, sanitize_filename

VIDEO_URL_PATTERN = re.compile(r'^https://rutube\.ru/video/[a-z0-9]{32}/$')

import os

os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["ALL_PROXY"] = ""
os.environ["NO_PROXY"] = "localhost,127.0.0.1"


class RutubeGateway:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def fetch_channel_videos(self, channel_url: str, progress_callback: Callable[[str], None] | None = None) -> tuple[ChannelInfo, list[str]]:
        normalized_url = self._normalize_channel_url(channel_url)
        links, title = self._fetch_with_selenium(normalized_url, progress_callback)
        if not links:
            raise RuntimeError('Не удалось получить список видео канала через Selenium')
        return ChannelInfo(source_url=normalized_url, name=title), sorted(set(links))

    def fetch_metadata_list(self, video_urls: list[str], cache_path: Path) -> list[VideoMetadata]:
        cached: dict[str, dict] = {}
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding='utf-8'))
        result: dict[str, dict] = dict(cached)
        updated = False
        total = len(video_urls)
        for index, url in enumerate(video_urls, start=1):
            video_id = url.rstrip('/').split('/')[-1]
            if video_id in cached:
                continue
            self.logger.info('Получаю метаданные видео %s/%s', index, total)
            info = self._fetch_metadata(url)
            if info:
                result[video_id] = info
                updated = True
        if updated or not cache_path.exists():
            cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return [VideoMetadata.from_raw(result[url.rstrip('/').split('/')[-1]]) for url in video_urls if url.rstrip('/').split('/')[-1] in result]

    def _normalize_channel_url(self, channel_url: str) -> str:
        base = channel_url.rstrip('/')
        return base if base.endswith('/videos') else f'{base}/videos'

    def _emit(self, callback: Callable[[str], None] | None, message: str) -> None:
        self.logger.info(message)
        if callback:
            callback(message)

    def _fetch_with_selenium(self, channel_url: str, progress_callback: Callable[[str], None] | None = None) -> tuple[list[str], str]:
        self._emit(progress_callback, 'Получаю список видео через Selenium...')
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager

        options = webdriver.ChromeOptions()
        options.add_argument("--no-proxy-server")
        options.add_argument("--proxy-server='direct://'")
        options.add_argument("--proxy-bypass-list=*")
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1280,720')
        options.add_argument('--log-level=3')
        options.add_argument('--no-proxy-server')
#        options.add_argument('--proxy-bypass-list=<-loopback>')

        self._emit(progress_callback, 'Запускаю браузер...')
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        try:
            self._emit(progress_callback, 'Открываю страницу канала...')
            driver.get(channel_url)
            time.sleep(2)
            title = 'Rutube Channel'
            try:
                raw_title = driver.find_element(By.XPATH, "//meta[@property='og:title']").get_attribute('content')
                title = raw_title.split('—')[0].strip()
            except Exception:
                pass

            links: set[str] = set()
            last_count = -1
            stable_rounds = 0
            max_rounds = 60
            self._emit(progress_callback, 'Прокручиваю страницу и собираю ссылки...')
            for step in range(1, max_rounds + 1):
                self._collect_links(driver, links)
                if len(links) != last_count:
                    last_count = len(links)
                    stable_rounds = 0
                    self._emit(progress_callback, f'Найдено видео: {len(links)} (шаг {step}/{max_rounds})')
                else:
                    stable_rounds += 1
                if stable_rounds >= 3:
                    break
                driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                time.sleep(1.2)
            self._collect_links(driver, links)
            self._emit(progress_callback, f'Сбор ссылок завершён. Найдено видео: {len(links)}')
            return sorted(links), sanitize_filename(title)
        finally:
            driver.quit()

    def _collect_links(self, driver, links: set[str]) -> None:
        selectors = ["a[href^='/video/'][href$='/']", "a[href*='/video/']"]
        for selector in selectors:
            for element in driver.find_elements(by='css selector', value=selector):
                href = element.get_attribute('href')
                if href and '/video/' in href:
                    href = href if href.endswith('/') else href + '/'
                    if VIDEO_URL_PATTERN.match(href):
                        links.add(href)

    def _fetch_metadata(self, video_url: str, retries: int = 3) -> dict | None:
        delays = [2, 5, 10]
        for attempt in range(retries):
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                    return ydl.extract_info(video_url, download=False)
            except Exception as exc:
                if attempt < retries - 1:
                    self.logger.warning('Ошибка получения метаданных %s. Повтор через %sс', video_url, delays[attempt])
                    time.sleep(delays[attempt])
                else:
                    self.logger.error('Не удалось получить метаданные %s: %s', video_url, exc)
        return None
