import logging

from app.rutube_gateway import RutubeGateway


def test_fetch_channel_uses_selenium(monkeypatch):
    logger = logging.getLogger('test_gateway')
    gateway = RutubeGateway(logger)

    def fake_fetch(url, progress_callback=None):
        return ['https://rutube.ru/video/' + 'a' * 32 + '/'], 'My Channel'

    monkeypatch.setattr(gateway, '_fetch_with_selenium', fake_fetch)
    channel, links = gateway.fetch_channel_videos('https://rutube.ru/channel/123')
    assert channel.name == 'My Channel'
    assert links == ['https://rutube.ru/video/' + 'a' * 32 + '/']
