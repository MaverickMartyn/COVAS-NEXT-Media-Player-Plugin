import sys
import platform
from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, TypedDict, final, override, Optional

from lib.Event import Event
from lib.EventManager import Projection
from lib.PluginHelper import PluginHelper
from lib.Logger import log
from .MediaControllerTypes import MediaPlaybackStateInner, default_media_playback_state, MediaControllerBase

if platform.system() == "Linux":
    from pydbus import SessionBus
    from threading import Thread, Event
else:
    SessionBus = None
    Thread = None
    Event = None
import time

class MPRISController(MediaControllerBase):
    def __init__(self):
        super().__init__()
        if SessionBus is None or Thread is None or Event is None:
            log('error', 'MPRISController requires pydbus and threading modules, which are not available on this platform.')
            raise NotImplementedError("MPRISController is not implemented for this platform.")
        self.bus = SessionBus()
        self.player = self._get_active_player()
        self._stop_event = Event()
        self._last_state: Optional[MediaPlaybackStateInner] = None
        self._poll_thread = Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _get_active_player(self):
        mpris_services = [name for name in self.bus.list_names() if name.startswith("org.mpris.MediaPlayer2.")]
        for name in mpris_services:
            try:
                player = self.bus.get(name, '/org/mpris/MediaPlayer2')
                if player.PlaybackStatus == "Playing":
                    return player
            except Exception:
                continue
        return self.bus.get(mpris_services[0], '/org/mpris/MediaPlayer2') if mpris_services else None

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                state = self.get_media_playback_state()
                if state != self._last_state:
                    self._last_state = state
                    if self.on_media_playback_info_changed:
                        self.on_media_playback_info_changed(state)
            except Exception:
                pass
            time.sleep(1)

    @override
    def play(self) -> bool:
        if self.player:
            self.player.Play()
            return True
        return False

    @override
    def pause(self) -> bool:
        if self.player:
            self.player.Pause()
            return True
        return False

    @override
    def stop(self) -> bool:
        if self.player:
            self.player.Stop()
            return True
        return False

    @override
    def prev_track(self) -> bool:
        if self.player:
            self.player.Previous()
            return True
        return False

    @override
    def next_track(self) -> bool:
        if self.player:
            self.player.Next()
            return True
        return False

    @override
    def get_media_playback_state(self) -> MediaPlaybackStateInner:
        if not self.player:
            return {
                "artist": None,
                "subtitle": None,
                "title": None,
                "is_shuffle_active": None,
                "auto_repeat_mode": None,
                "playback_status": None
            }

        metadata = self.player.Metadata
        playback_status = self.player.PlaybackStatus
        shuffle = getattr(self.player, "Shuffle", None)
        loop_status = getattr(self.player, "LoopStatus", None)

        return {
            "artist": (metadata.get("xesam:artist") or [None])[0],
            "subtitle": metadata.get("xesam:album"),
            "title": metadata.get("xesam:title"),
            "is_shuffle_active": bool(shuffle) if shuffle is not None else None,
            "auto_repeat_mode": loop_status == "Track" if loop_status is not None else None,
            "playback_status": playback_status
        }

    @override
    def cleanup(self):
        self._stop_event.set()
        self._poll_thread.join(timeout=2)
