from pathlib import Path

from app.rutube_config import ConfigManager
from app.rutube_models import AppSettings


def test_config_load_supports_max_workers(tmp_path: Path):
    config_path = tmp_path / 'rutube_config.json'
    config_path.write_text('{"last_url":"u","download_folder":"d","concurrent_fragment_count":3,"max_workers":5}', encoding='utf-8')
    settings = ConfigManager(config_path).load()
    assert settings.max_parallel_downloads == 5
    assert settings.concurrent_fragment_count == 3


def test_config_save_writes_max_workers(tmp_path: Path):
    config_path = tmp_path / 'rutube_config.json'
    manager = ConfigManager(config_path)
    manager.save(AppSettings(download_folder=tmp_path, concurrent_fragment_count=2, max_parallel_downloads=4, last_url='x'))
    content = config_path.read_text(encoding='utf-8')
    assert '"max_workers": 4' in content
