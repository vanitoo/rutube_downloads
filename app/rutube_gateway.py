from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Callable

from urllib.parse import urljoin, urlsplit

import requests
import yt_dlp

from app.rutube_models import ChannelInfo, VideoMetadata, sanitize_filename

class RutubeGateway:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def fetch_channel_videos(self, channel_url: str, progress_callback: Callable[[str], None] | None = None) -> tuple[ChannelInfo, list[str]]:
        normalized_url = self._normalize_channel_url(channel_url)
        try:
            links, title = self._fetch_with_api(normalized_url, progress_callback)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            self._emit(progress_callback, f'API недоступен: {exc}. Пробую yt-dlp...')
            links, title = self._fetch_with_ytdlp(normalized_url, progress_callback)
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
        parsed = urlsplit(channel_url.strip())
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('rutube.ru', 'www.rutube.ru'):
            raise ValueError('Укажите ссылку на канал Rutube')
        path = parsed.path.rstrip('/')
        if not re.fullmatch(r'/(?:channel/\d+|u/[\w-]+)(?:/(?:videos|shorts))?', path):
            raise ValueError('Неподдерживаемая ссылка на канал Rutube')
        if not path.endswith(('/videos', '/shorts')):
            path += '/videos'
        return 'https://rutube.ru' + path

    def _emit(self, callback: Callable[[str], None] | None, message: str) -> None:
        self.logger.info(message)
        if callback:
            callback(message)

    def _fetch_with_api(self, channel_url: str, progress_callback=None) -> tuple[list[str], str]:
        match = re.fullmatch(r'/channel/(\d+)/(videos|shorts)', urlsplit(channel_url).path)
        if not match:
            return self._fetch_with_ytdlp(channel_url, progress_callback)
        channel_id, section = match.groups()
        origin = 'rshorts' if section == 'shorts' else 'rtb,rst,ifrm,rspa'
        url = f'https://rutube.ru/api/video/person/{channel_id}/?page=1&format=json&origin__type={origin}'
        title = None
        links: set[str] = set()
        visited: set[str] = set()
        with requests.Session() as session:
            session.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
            while url:
                if url in visited or urlsplit(url).netloc != 'rutube.ru' or urlsplit(url).scheme != 'https':
                    raise RuntimeError('Некорректная ссылка следующей страницы API')
                visited.add(url)
                self._emit(progress_callback, f'Rutube API: страница {len(visited)}')
                response = session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get('results'), list):
                    raise ValueError('Неожиданный формат ответа Rutube API')
                for item in data['results']:
                    if not isinstance(item, dict):
                        continue
                    video_id = str(item.get('id') or '')
                    if re.fullmatch(r'[a-f0-9]{32}', video_id):
                        links.add(f'https://rutube.ru/video/{video_id}/')
                    author = item.get('author')
                    if not title and isinstance(author, dict):
                        title = author.get('name')
                self._emit(progress_callback, f'Найдено видео: {len(links)}')
                next_url = data.get('next')
                if data.get('has_next') and not next_url:
                    raise RuntimeError('API не вернул следующую страницу')
                url = urljoin(url, next_url) if next_url and data.get('has_next', True) else None
        return sorted(links), sanitize_filename(title or f'Rutube {channel_id}')

    def _fetch_with_ytdlp(self, channel_url: str, progress_callback=None) -> tuple[list[str], str]:
        self._emit(progress_callback, 'Получаю список видео через yt-dlp...')
        with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True, 'skip_download': True,
                               'socket_timeout': 30}) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            if not info or 'entries' not in info:
                raise RuntimeError('yt-dlp не вернул список видео')
            links = set()
            title = info.get('channel') or info.get('uploader')
            for entry in info['entries'] or []:
                if not entry:
                    continue
                video_id = str(entry.get('id') or '')
                if re.fullmatch(r'[a-f0-9]{32}', video_id):
                    links.add(f'https://rutube.ru/video/{video_id}/')
                title = title or entry.get('channel') or entry.get('uploader')
            self._emit(progress_callback, f'Найдено видео: {len(links)}')
            return sorted(links), sanitize_filename(title or info.get('title') or 'Rutube Channel')

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
