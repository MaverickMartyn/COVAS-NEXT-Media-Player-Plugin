from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, TypedDict, final, override

from pydantic import BaseModel

from lib.Logger import log

class MediaPlaybackStateInner(BaseModel):
    artist: str | None = None
    subtitle: str | None = None
    title: str | None = None
    is_shuffle_active: bool | None = None
    is_muted: bool | None = None
    auto_repeat_mode: str | None = None
    playback_status: str | None = None
    volume: int | None = None

def default_media_playback_state() -> MediaPlaybackStateInner:
    return MediaPlaybackStateInner(
        artist=None,
        subtitle=None,
        title=None,
        is_shuffle_active=None,
        is_muted=None,
        auto_repeat_mode=None,
        playback_status=None,
        volume=None
    )

class MediaControllerBase(ABC):
    on_media_playback_info_changed: Callable[[MediaPlaybackStateInner], None] | None = None
    def __init__(self):
        super().__init__()
    @abstractmethod
    def play(self) -> str: pass
    @abstractmethod
    def pause(self) -> str: pass
    @abstractmethod
    def stop(self) -> str: pass
    @abstractmethod
    def prev_track(self) -> str: pass
    @abstractmethod
    def next_track(self) -> str: pass
    @abstractmethod
    def get_media_playback_state(self) -> MediaPlaybackStateInner: pass
    @abstractmethod
    def cleanup(self): pass
    @abstractmethod
    def start_playlist(self, path: str) -> str: pass
