import logging
from pathlib import Path

from app.rutube_downloader import RutubeDownloader
from app.rutube_models import AppSettings, ChannelInfo, DownloadStatus, VideoMetadata


class FakeGateway:
    def fetch_channel_videos(self, channel_url, progress_callback=None):
        if progress_callback:
            progress_callback('step')
        return ChannelInfo(source_url=channel_url, name='Channel'), ['https://rutube.ru/video/' + 'a' * 32 + '/']

    def fetch_metadata_list(self, video_urls, cache_path):
        return [VideoMetadata(video_id='id1', title='Title', webpage_url=video_urls[0])]


class FakeStorage:
    def __init__(self):
        self.saved_snapshot = False
        self.saved_description = False
        self.saved_thumbnail = False

    def ensure_channel_folder(self, settings, channel):
        return Path('/tmp/channel')

    def video_exists(self, channel_folder, metadata):
        return False

    def save_description(self, channel_folder, metadata):
        self.saved_description = True

    def save_thumbnail(self, channel_folder, metadata):
        self.saved_thumbnail = True

    def save_metadata_snapshot(self, channel_folder, videos):
        self.saved_snapshot = True


def test_get_channel_videos_saves_snapshot():
    downloader = RutubeDownloader(FakeGateway(), FakeStorage(), logging.getLogger('test_downloader'))
    channel, folder, videos = downloader.get_channel_videos('https://rutube.ru/channel/1', AppSettings(download_folder=Path('/tmp')))
    assert channel.name == 'Channel'
    assert folder == Path('/tmp/channel')
    assert len(videos) == 1


def test_download_skips_existing_video():
    class ExistingStorage(FakeStorage):
        def video_exists(self, channel_folder, metadata):
            return True

    statuses = []
    downloader = RutubeDownloader(FakeGateway(), ExistingStorage(), logging.getLogger('test_downloader'))
    video = VideoMetadata(video_id='id1', title='Title', webpage_url='https://rutube.ru/video/' + 'a' * 32 + '/')
    downloader.download_videos(
        [video],
        Path('/tmp/channel'),
        AppSettings(download_folder=Path('/tmp')),
        status_callback=lambda index, status, percent, message: statuses.append((index, status, percent, message)),
    )
    assert statuses[0][1] == DownloadStatus.SKIPPED
