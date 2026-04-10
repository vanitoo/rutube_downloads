from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import requests

from app.rutube_models import AppSettings, ChannelInfo, VideoMetadata


class LocalStorage:
    def __init__(self, logger):
        self.logger = logger

    def ensure_channel_folder(self, settings: AppSettings, channel: ChannelInfo) -> Path:
        folder = Path(settings.download_folder) / channel.safe_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def video_exists(self, channel_folder: Path, metadata: VideoMetadata) -> bool:
        return (channel_folder / metadata.mp4_filename).exists()

    def save_description(self, channel_folder: Path, metadata: VideoMetadata) -> None:
        (channel_folder / metadata.txt_filename).write_text(metadata.description or '', encoding='utf-8')

    def save_thumbnail(self, channel_folder: Path, metadata: VideoMetadata) -> None:
        if not metadata.thumbnail_url:
            return
        response = requests.get(metadata.thumbnail_url, timeout=30)
        response.raise_for_status()
        (channel_folder / metadata.jpg_filename).write_bytes(response.content)

    def save_metadata_snapshot(self, channel_folder: Path, videos: Iterable[VideoMetadata]) -> None:
        rows = [video.raw or {
            'id': video.video_id,
            'title': video.title,
            'webpage_url': video.webpage_url,
            'upload_date': video.upload_date,
            'duration_string': video.duration_string,
        } for video in videos]
        if not rows:
            return
        keys = sorted({key for row in rows for key in row.keys()})
        with (channel_folder / 'metadata.csv').open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)

    def open_file(self, file_path: Path) -> None:
        if sys.platform.startswith('win'):
            os.startfile(str(file_path))  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(file_path)])
        else:
            subprocess.Popen(['xdg-open', str(file_path)])
