import logging
from unittest.mock import MagicMock

import requests

from app.rutube_gateway import RutubeGateway


def test_api_pagination(monkeypatch):
    gateway = RutubeGateway(logging.getLogger('test_gateway'))
    session = MagicMock()
    session.__enter__.return_value = session
    first = {'results': [{'id': 'a' * 32, 'author': {'name': 'My Channel'}}],
             'has_next': True, 'next': '/api/video/person/123/?page=2'}
    second = {'results': [{'id': 'a' * 32}, {'id': 'b' * 32}], 'has_next': False}
    session.get.side_effect = [MagicMock(**{'json.return_value': first}),
                               MagicMock(**{'json.return_value': second})]
    monkeypatch.setattr(requests, 'Session', lambda: session)
    channel, links = gateway.fetch_channel_videos('https://rutube.ru/channel/123')
    assert channel.name == 'My Channel'
    assert links == [f'https://rutube.ru/video/{c * 32}/' for c in 'ab']
    assert session.get.call_count == 2


def test_api_failure_falls_back(monkeypatch):
    gateway = RutubeGateway(logging.getLogger('test_gateway'))
    def fail(*args):
        raise requests.ConnectionError('offline')
    monkeypatch.setattr(gateway, '_fetch_with_api', fail)
    monkeypatch.setattr(gateway, '_fetch_with_ytdlp',
                        lambda *args: (['https://rutube.ru/video/' + 'a' * 32 + '/'], 'My Channel'))
    channel, links = gateway.fetch_channel_videos('https://rutube.ru/channel/123')
    assert channel.name == 'My Channel'
    assert len(links) == 1
