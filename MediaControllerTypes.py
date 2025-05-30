from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, TypedDict, final, override

from lib.Logger import log

class MediaPlaybackStateInner(TypedDict):
    artist: str | None
    subtitle: str | None
    title: str | None
    is_shuffle_active: bool | None
    auto_repeat_mode: bool | None
    playback_status: str | None

def default_media_playback_state() -> MediaPlaybackStateInner:
    return MediaPlaybackStateInner(
        artist=None,
        subtitle=None,
        title=None,
        is_shuffle_active=False,
        auto_repeat_mode=False,
        playback_status=None
    )

class MediaControllerBase(ABC):
    on_media_playback_info_changed: Callable[[MediaPlaybackStateInner], None] | None = None
    def __init__(self):
        super().__init__()
    @abstractmethod
    def play(self) -> bool: pass
    @abstractmethod
    def pause(self) -> bool: pass
    @abstractmethod
    def stop(self) -> bool: pass
    @abstractmethod
    def prev_track(self) -> bool: pass
    @abstractmethod
    def next_track(self) -> bool: pass
    @abstractmethod
    def get_media_playback_state(self) -> MediaPlaybackStateInner: pass
    @abstractmethod
    def cleanup(self): pass
