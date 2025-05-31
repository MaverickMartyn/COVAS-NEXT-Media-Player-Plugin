import json
import dbus_next
from dbus_next.introspection import Interface, Node
from dbus_next.aio.proxy_object import ProxyInterface, ProxyObject
import platform
import asyncio
import sys
from threading import Thread, Event
from typing import List, Optional, cast
from .MediaControllerTypes import MediaPlaybackStateInner, default_media_playback_state, MediaControllerBase
from lib.Logger import log

if platform.system() == "Linux":
    from dbus_next.aio.message_bus import MessageBus
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
        if not MessageBus:
            log('error', 'MPRISController requires dbus-next, which is not available on this platform.')
            raise NotImplementedError("MPRISController is not implemented for this platform.")
        
        self._bus = await MessageBus().connect()
        names = await self._list_names()
        mpris_names = [name for name in names if name.startswith("org.mpris.MediaPlayer2.")]
        log('debug', f'MPRIS names found: {mpris_names}')
        for name in mpris_names:
            try:
                introspection: Node = await self._bus.introspect(name, "/org/mpris/MediaPlayer2")
                proxy_obj: ProxyObject = self._bus.get_proxy_object(name, "/org/mpris/MediaPlayer2", introspection)
                player_iface: ProxyInterface = proxy_obj.get_interface("org.mpris.MediaPlayer2.Player")
                
                status = await player_iface.get_playback_status()
                log('debug', f'Player {name} status: {status}')
                if status == "Playing":
                    self._player_iface = player_iface
                    return
            except Exception:
                log('debug', f'Failed to introspect or get player interface for {name}, continuing...')
                log('debug', f'Exception details: {sys.exc_info()[1]}')
                continue
        # fallback to first player found
        if mpris_names:
            log('debug', 'No active MPRIS player found, using the first available player.')
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
                log('debug', f'Media playback state changed: {state}')
                self._last_state = state
                if self.on_media_playback_info_changed:
                    self.on_media_playback_info_changed(state)
        except Exception:
            log('error', 'Error while polling media playback state')
            log('debug', f'Exception details: {sys.exc_info()[1]}')
            pass

    async def _get_media_playback_state(self) -> MediaPlaybackStateInner:
        if not self._player_iface:
            log('debug', 'No player interface available, returning default state')
            return default_media_playback_state()
        try:
            metadata = await self._player_iface.get_metadata()
            playback_status = await self._player_iface.get_playback_status()

            # Fix the Shuffle property, since VLC is being stupid.
            introspection: Node = self._player_iface.introspection
            for prop in introspection.properties:
                # log('debug', vars(prop))
                if prop.name == "Shuffle" and prop.signature == "d":
                    # log('debug', f'Found Incorrect Shuffle property: {prop.name} with type {prop.signature}. Fixing to boolean.')
                    # Fix the type of Shuffle property to boolean
                    prop.signature = "b"
                    
            shuffle = cast(bool, await self._player_iface.get_shuffle()) if hasattr(self._player_iface, 'get_shuffle') else None
            # if hasattr(self._player_iface, 'get_shuffle'):
            #     log('debug', f'get_shuffle: {shuffle}')
            loop_status = await self._player_iface.get_loop_status() if hasattr(self._player_iface, 'get_loop_status') else None
            # shuffle = False
            # loop_status = None
            artists_list = cast(list[str], (cast(dbus_next.signature.Variant, metadata.get("xesam:artist")) or {"value":None}).value)

            # Concatenate artists
            artists = ', '.join(artists_list) if artists_list else None

            return {
                "artist": artists,
                "subtitle": cast(str, (cast(dbus_next.signature.Variant, metadata.get("xesam:album")) or {"value":None}).value),
                "title": cast(str, (cast(dbus_next.signature.Variant, metadata.get("xesam:title")) or {"value":None}).value),
                "is_shuffle_active": bool(shuffle) if shuffle is not None else None,
                "auto_repeat_mode": loop_status == "Track" if loop_status is not None else None,
                "playback_status": playback_status
            }
        except Exception:
            log('error', 'Error getting media playback state')
            log('debug', f'Exception details: {sys.exc_info()[1]}')
            # Print exception location for debugging
            log('debug', f'Exception location: {sys.exc_info()[2].tb_frame.f_code.co_filename}:{sys.exc_info()[2].tb_lineno}')
            return default_media_playback_state()

    # async def _safe_get_property(self, prop):
    #     try:
    #         return await self._player_iface.get_property(prop)
    #     except Exception:
    #         return None

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
