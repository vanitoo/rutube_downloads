from __future__ import annotations

import concurrent.futures
import logging
import threading
from pathlib import Path
from typing import Callable

import yt_dlp

from app.rutube_models import AppSettings, ChannelInfo, DownloadStatus, VideoMetadata
from app.rutube_gateway import RutubeGateway
from app.rutube_storage import LocalStorage


class RutubeYTDLogger:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def debug(self, msg: str) -> None:
        if msg.strip():
            self.logger.debug(msg)

    def info(self, msg: str) -> None:
        self.logger.info(msg)

    def warning(self, msg: str) -> None:
        self.logger.warning(msg)

    def error(self, msg: str) -> None:
        self.logger.error(msg)


class RutubeDownloader:
    def __init__(self, gateway: RutubeGateway, storage: LocalStorage, logger: logging.Logger):
        self.gateway = gateway
        self.storage = storage
        self.logger = logger
        self._cancel_flag = False
        self._cancel_lock = threading.Lock()

    def cancel_download(self) -> None:
        with self._cancel_lock:
            self._cancel_flag = True

    def reset_cancel(self) -> None:
        with self._cancel_lock:
            self._cancel_flag = False

    def is_cancelled(self) -> bool:
        with self._cancel_lock:
            return self._cancel_flag

    def get_channel_videos(
        self,
        channel_url: str,
        settings: AppSettings,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[ChannelInfo, Path, list[VideoMetadata]]:
        channel, links = self.gateway.fetch_channel_videos(channel_url, progress_callback=progress_callback)
        folder = self.storage.ensure_channel_folder(settings, channel)
        videos = self.gateway.fetch_metadata_list(links, folder / 'metadata.json')
        self.storage.save_metadata_snapshot(folder, videos)
        return channel, folder, videos

    def download_videos(
        self,
        videos: list[VideoMetadata],
        channel_folder: Path,
        settings: AppSettings,
        status_callback: Callable[[int, DownloadStatus, int, str | None], None] | None = None,
        progress_callback: Callable[[int, dict, int], None] | None = None,
    ) -> None:
        self.reset_cancel()
        total = len(videos)
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.max_parallel_downloads) as executor:
            futures = {
                executor.submit(self._download_one, index, video, channel_folder, settings, status_callback, progress_callback, total): index
                for index, video in enumerate(videos)
            }
            for future in concurrent.futures.as_completed(futures):
                if self.is_cancelled():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                future.result()

    def _download_one(
        self,
        index: int,
        metadata: VideoMetadata,
        channel_folder: Path,
        settings: AppSettings,
        status_callback: Callable[[int, DownloadStatus, int, str | None], None] | None,
        progress_callback: Callable[[int, dict, int], None] | None,
        total: int,
    ) -> None:
        if self.is_cancelled():
            if status_callback:
                status_callback(index, DownloadStatus.CANCELLED, 0, None)
            return
        if self.storage.video_exists(channel_folder, metadata):
            if status_callback:
                status_callback(index, DownloadStatus.SKIPPED, 100, 'Файл уже существует')
            return

        if status_callback:
            status_callback(index, DownloadStatus.DOWNLOADING, 0, None)

        filename = channel_folder / metadata.mp4_filename
        state: dict[str, int | None] = {'last_fragment': None, 'last_percent': -1}

        def hook(data: dict) -> None:
            if self.is_cancelled():
                raise yt_dlp.utils.DownloadCancelled('Загрузка отменена пользователем')
            if progress_callback:
                progress_callback(index, data, total)
            if data.get('status') == 'downloading':
                fragment_index = data.get('fragment_index')
                fragment_count = data.get('fragment_count')
                downloaded = data.get('downloaded_bytes') or 0
                total_bytes = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
                percent = int(downloaded * 100 / total_bytes) if total_bytes else None
                should_log = False
                if fragment_index and fragment_index != state['last_fragment']:
                    state['last_fragment'] = fragment_index
                    should_log = True
                elif percent is not None and abs(percent - int(state['last_percent'] or -1)) >= 5:
                    state['last_percent'] = percent
                    should_log = True
                if should_log:
                    if fragment_index and fragment_count:
                        suffix = f'Фрагмент {fragment_index}/{fragment_count}'
                        if percent is not None:
                            suffix += f' ({percent}%)'
                    elif percent is not None:
                        suffix = f'{percent}%'
                    else:
                        suffix = 'загрузка...'
                    self.logger.info('Скачивание "%s": %s', metadata.title, suffix)
            elif data.get('status') == 'finished':
                self.logger.info('Скачивание "%s": файл собран, постобработка...', metadata.title)

        options = {
            'outtmpl': str(filename),
            'quiet': True,
            'no_warnings': True,
            'logger': RutubeYTDLogger(self.logger),
            'progress_hooks': [hook],
            'concurrent_fragment_count': settings.concurrent_fragment_count,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([metadata.webpage_url])
            self.storage.save_description(channel_folder, metadata)
            self.storage.save_thumbnail(channel_folder, metadata)
            if status_callback:
                status_callback(index, DownloadStatus.COMPLETED, 100, None)
        except yt_dlp.utils.DownloadCancelled:
            if status_callback:
                status_callback(index, DownloadStatus.CANCELLED, 0, 'Загрузка отменена')
        except Exception as exc:
            self.logger.exception('Ошибка скачивания %s: %s', metadata.title, exc)
            if status_callback:
                status_callback(index, DownloadStatus.FAILED, 0, str(exc))
