import platform
import asyncio
from threading import Thread, Event
from typing import Optional
from .MediaControllerTypes import MediaPlaybackStateInner, default_media_playback_state, MediaControllerBase
from lib.Logger import log

if platform.system() == "Linux":
    from dbus_next.aio import MessageBus
    from dbus_next.constants import BusType
else:
    MessageBus = None

import time


class MPRISController(MediaControllerBase):
    def __init__(self):
        super().__init__()
        if MessageBus is None:
            log('error', 'MPRISController requires dbus-next, which is not available on this platform.')
            raise NotImplementedError("MPRISController is not implemented for this platform.")

        self._loop = asyncio.new_event_loop()
        self._stop_event = Event()
        self._last_state: Optional[MediaPlaybackStateInner] = None
        self._player_iface = None

        self._poll_thread = Thread(target=self._run, daemon=True)
        self._poll_thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._init_player())
        while not self._stop_event.is_set():
            self._loop.run_until_complete(self._poll())
            time.sleep(1)

    async def _init_player(self):
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        names = await self._list_names()
        mpris_names = [name for name in names if name.startswith("org.mpris.MediaPlayer2.")]
        for name in mpris_names:
            try:
                introspection = await self._bus.introspect(name, "/org/mpris/MediaPlayer2")
                proxy_obj = self._bus.get_proxy_object(name, "/org/mpris/MediaPlayer2", introspection)
                player_iface = proxy_obj.get_interface("org.mpris.MediaPlayer2.Player")
                status = await player_iface.get_property("PlaybackStatus")
                if status == "Playing":
                    self._player_iface = player_iface
                    return
            except Exception:
                continue
        # fallback to first player found
        if mpris_names:
            introspection = await self._bus.introspect(mpris_names[0], "/org/mpris/MediaPlayer2")
            proxy_obj = self._bus.get_proxy_object(mpris_names[0], "/org/mpris/MediaPlayer2", introspection)
            self._player_iface = proxy_obj.get_interface("org.mpris.MediaPlayer2.Player")

    async def _list_names(self):
        introspection = await self._bus.introspect("org.freedesktop.DBus", "/org/freedesktop/DBus")
        proxy = self._bus.get_proxy_object("org.freedesktop.DBus", "/org/freedesktop/DBus", introspection)
        iface = proxy.get_interface("org.freedesktop.DBus")
        return await iface.call_list_names()

    async def _poll(self):
        if not self._player_iface:
            return
        try:
            state = await self._get_media_playback_state()
            if state != self._last_state:
                self._last_state = state
                if self.on_media_playback_info_changed:
                    self.on_media_playback_info_changed(state)
        except Exception:
            pass

    async def _get_media_playback_state(self) -> MediaPlaybackStateInner:
        metadata = await self._player_iface.get_property("Metadata")
        playback_status = await self._player_iface.get_property("PlaybackStatus")
        shuffle = await self._safe_get_property("Shuffle")
        loop_status = await self._safe_get_property("LoopStatus")

        return {
            "artist": (metadata.get("xesam:artist") or [None])[0],
            "subtitle": metadata.get("xesam:album"),
            "title": metadata.get("xesam:title"),
            "is_shuffle_active": bool(shuffle) if shuffle is not None else None,
            "auto_repeat_mode": loop_status == "Track" if loop_status is not None else None,
            "playback_status": playback_status
        }

    async def _safe_get_property(self, prop):
        try:
            return await self._player_iface.get_property(prop)
        except Exception:
            return None

    @staticmethod
    def _run_coroutine_in_loop(loop, coro):
        asyncio.run_coroutine_threadsafe(coro, loop)

    def play(self) -> bool:
        if self._player_iface:
            self._run_coroutine_in_loop(self._loop, self._player_iface.call_play())
            return True
        return False

    def pause(self) -> bool:
        if self._player_iface:
            self._run_coroutine_in_loop(self._loop, self._player_iface.call_pause())
            return True
        return False

    def stop(self) -> bool:
        if self._player_iface:
            self._run_coroutine_in_loop(self._loop, self._player_iface.call_stop())
            return True
        return False

    def prev_track(self) -> bool:
        if self._player_iface:
            self._run_coroutine_in_loop(self._loop, self._player_iface.call_previous())
            return True
        return False

    def next_track(self) -> bool:
        if self._player_iface:
            self._run_coroutine_in_loop(self._loop, self._player_iface.call_next())
            return True
        return False

    def get_media_playback_state(self) -> MediaPlaybackStateInner:
        return self._last_state or default_media_playback_state()

    def cleanup(self):
        self._stop_event.set()
        self._poll_thread.join(timeout=2)
        self._loop.stop()
