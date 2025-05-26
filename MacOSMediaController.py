from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, TypedDict, final, override

from lib.Event import Event
from lib.EventManager import Projection
from lib.PluginHelper import PluginHelper
from lib.Logger import log
from .MediaControllerTypes import MediaPlaybackStateInner, default_media_playback_state, MediaControllerBase


class MacOSMediaController(MediaControllerBase):
    # macOS backend
    @override
    def play(self) -> bool: return False  # Placeholder implementation
    @override
    def pause(self) -> bool: return False # Placeholder implementation
    @override
    def stop(self) -> bool: return False # Placeholder implementation
    @override
    def prev_track(self) -> bool: return False # Placeholder implementation
    @override
    def next_track(self) -> bool: return False # Placeholder implementation
    @override
    def get_media_playback_state(self) -> MediaPlaybackStateInner: return default_media_playback_state() # Placeholder implementation
    @override
    def cleanup(self): pass