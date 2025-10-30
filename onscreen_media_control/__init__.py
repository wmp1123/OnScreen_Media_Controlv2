from .ui import MediaController
MediaOverlay = MediaController

from .media_backend import get_current_media
from .utils import send_key, VK_MEDIA_PLAY_PAUSE, VK_MEDIA_NEXT_TRACK, VK_MEDIA_PREV_TRACK

__all__ = [
    "MediaController",
    "MediaOverlay",
    "get_current_media",
    "send_key",
    "VK_MEDIA_PLAY_PAUSE",
    "VK_MEDIA_NEXT_TRACK",
    "VK_MEDIA_PREV_TRACK",
]
