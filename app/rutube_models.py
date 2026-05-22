from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import re

INVALID_FILENAME_CHARS = r'[\\/*?:"<>|]'


def sanitize_filename(name: str) -> str:
    sanitized = re.sub(INVALID_FILENAME_CHARS, '_', name or '').strip()
    return sanitized or 'untitled'


class DownloadStatus(str, Enum):
    PENDING = '⏳'
    DOWNLOADING = '⬇️ В процессе'
    COMPLETED = '✅ Готово'
    FAILED = '❌ Ошибка'
    CANCELLED = '🛑 Отменено'
    SKIPPED = '⏭ Пропущено'


@dataclass(frozen=True)
class ChannelInfo:
    source_url: str
    name: str

    @property
    def safe_name(self) -> str:
        return sanitize_filename(self.name)


@dataclass(frozen=True)
class VideoMetadata:
    video_id: str
    title: str
    webpage_url: str
    upload_date: str = '00000000'
    duration_string: str = '00:00'
    description: str = ''
    thumbnail_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def safe_title(self) -> str:
        return sanitize_filename(re.sub(r'\.(mp4|mkv|avi|mov)$', '', self.title, flags=re.IGNORECASE))

    @property
    def date_prefix(self) -> str:
        raw = (self.upload_date or '00000000').replace('.', '')
        if len(raw) != 8 or not raw.isdigit():
            return '0000.00.00'
        return f'{raw[:4]}.{raw[4:6]}.{raw[6:8]}'

    @property
    def time_prefix(self) -> str:
        digits = (self.duration_string or '00:00').replace(':', '')
        digits = digits.zfill(4)[-4:]
        return digits

    @property
    def file_prefix(self) -> str:
        return f'{self.date_prefix}_{self.time_prefix}_'

    @property
    def mp4_filename(self) -> str:
        return f'{self.file_prefix}{self.video_id}_{self.safe_title}.mp4'

    @property
    def txt_filename(self) -> str:
        return f'{self.file_prefix}{self.video_id}_{self.safe_title}.txt'

    @property
    def jpg_filename(self) -> str:
        return f'{self.file_prefix}{self.video_id}_{self.safe_title}.jpg'

    @property
    def formatted_date(self) -> str:
        return self.date_prefix

    @property
    def formatted_duration(self) -> str:
        return self.duration_string or '00:00'

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> 'VideoMetadata':
        webpage_url = raw.get('webpage_url') or raw.get('url') or ''
        video_id = raw.get('id') or webpage_url.rstrip('/').split('/')[-1]
        return cls(
            video_id=video_id,
            title=raw.get('title', 'Без названия'),
            webpage_url=webpage_url,
            upload_date=raw.get('upload_date', '00000000'),
            duration_string=raw.get('duration_string', '00:00'),
            description=raw.get('description', ''),
            thumbnail_url=raw.get('thumbnail'),
            raw=dict(raw),
        )


@dataclass(frozen=True)
class AppSettings:
    download_folder: Path
    concurrent_fragment_count: int = 4
    max_parallel_downloads: int = 1
    last_url: str = ''

    def normalized(self) -> 'AppSettings':
        return AppSettings(
            download_folder=Path(self.download_folder),
            concurrent_fragment_count=max(1, int(self.concurrent_fragment_count)),
            max_parallel_downloads=max(1, int(self.max_parallel_downloads)),
            last_url=self.last_url,
        )
