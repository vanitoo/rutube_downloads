# Version:5
from rutube_downloader import RutubeDownloader
from rutube_gui import create_gui

if __name__ == "__main__":
    downloader = RutubeDownloader()
    create_gui(downloader)
