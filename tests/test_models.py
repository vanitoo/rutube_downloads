from app.rutube_models import VideoMetadata, sanitize_filename


def test_sanitize_filename_replaces_invalid_chars():
    assert sanitize_filename('a:b/c*?') == 'a_b_c__'


def test_video_filename_formatting():
    video = VideoMetadata(
        video_id='1',
        title='Demo Video.mp4',
        webpage_url='https://rutube.ru/video/1/',
        upload_date='20260410',
        duration_string='12:34',
    )
    assert video.mp4_filename == '2026.04.10_1234_Demo Video.mp4'
    assert video.txt_filename.endswith('.txt')
