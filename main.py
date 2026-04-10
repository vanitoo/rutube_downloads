from __future__ import annotations

from pathlib import Path

from app.rutube_config import ConfigManager
from app.rutube_downloader import RutubeDownloader
from app.rutube_gateway import RutubeGateway
from app.rutube_gui import create_gui
from app.rutube_logger import logger
from app.rutube_storage import LocalStorage


if __name__ == '__main__':
    base_path = Path(__file__).resolve().parent
    app_logger = logger.setup(base_path / 'rutube_app.log')
    config_manager = ConfigManager(base_path / 'rutube_config.json')
    storage = LocalStorage(app_logger)
    gateway = RutubeGateway(app_logger)
    downloader = RutubeDownloader(gateway, storage, app_logger)
    app = create_gui(downloader, config_manager, storage)
    app.run()
