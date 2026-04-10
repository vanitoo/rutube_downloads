from __future__ import annotations

import json
from pathlib import Path

from app.rutube_models import AppSettings


class ConfigManager:
    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)

    def load(self) -> AppSettings:
        if not self.config_path.exists():
            return AppSettings(download_folder=Path('rutube_downloads')).normalized()
        raw = json.loads(self.config_path.read_text(encoding='utf-8'))
        return AppSettings(
            last_url=raw.get('last_url', ''),
            download_folder=Path(raw.get('download_folder', 'rutube_downloads')),
            concurrent_fragment_count=raw.get('concurrent_fragment_count', 4),
            max_parallel_downloads=raw.get('max_workers', raw.get('max_parallel_downloads', 1)),
        ).normalized()

    def save(self, settings: AppSettings) -> None:
        self.config_path.write_text(json.dumps({
            'last_url': settings.last_url,
            'download_folder': str(settings.download_folder),
            'concurrent_fragment_count': settings.concurrent_fragment_count,
            'max_workers': settings.max_parallel_downloads,
        }, ensure_ascii=False, indent=2), encoding='utf-8')
