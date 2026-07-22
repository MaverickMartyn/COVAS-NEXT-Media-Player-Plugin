from asyncio.events import TimerHandle

from dbus_next.message import Message
from math import floor
import dbus_next
from dbus_next.aio.message_bus import MessageBus
import json
from dbus_next import message
from dbus_next.constants import MessageType

import platform
import asyncio
import sys
from threading import Thread, Event
from typing import Any, List, Optional, cast, override

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

        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._stop_event: Event = Event()
        self._thread = Thread(target=self._run_loop, daemon=True)

        self._notify_handle: TimerHandle | None = None
        self._last_state: Optional[MediaPlaybackStateInner] = None
        self._current_player_name: str | None = None
        
        log('debug', 'Starting MPRISController event loop thread.')
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._init_player(), self._loop).result(timeout=10)
        log('debug', 'MPRISController initialized.')

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _init_player(self):
        log('debug', 'Executing _init_player()')
        if not MessageBus:
            log('error', 'MPRISController requires dbus-next, which is not available on this platform.')
            raise NotImplementedError("MPRISController is not implemented for this platform.")

        self._bus = await MessageBus().connect()

        reply = await self._bus.call(
            message.Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="ListNames"
            )
        )

        if reply is None:
            log('error', 'Failed to retrieve MPRIS names from D-Bus.')
            raise RuntimeError("Failed to retrieve MPRIS names from D-Bus.")

        mpris_names = [
            name
            for name in reply.body[0]
            if name.startswith("org.mpris.MediaPlayer2.")
        ]
        log('debug', f'MPRIS names found: {mpris_names}')
        status: str | None = None
        
        for name in mpris_names:
            try:
                status = await self._get_property(
                    service=name,
                    interface="org.mpris.MediaPlayer2.Player",
                    property_name="PlaybackStatus"
                )
                log('debug', f'Player {name} status: {status}')
                if status == "Playing":
                    self._current_player_name = name
                    break
            except Exception:
                log('debug', f'Failed to get current playback status for {name}, continuing...')
                log('debug', f'Exception details: {sys.exc_info()[1]}')
                continue
            
        # fallback to first player found
        if self._current_player_name is None and mpris_names:
            log('debug', 'No active MPRIS player found, using the first available player.')
            self._current_player_name = mpris_names[0]
            if self._current_player_name:
                status = await self._get_property(
                    service=self._current_player_name,
                    interface="org.mpris.MediaPlayer2.Player",
                    property_name="PlaybackStatus"
                )

        # Add a message handler to listen for property changes
        await self._bus.call(
            message.Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=["type='signal',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',path='/org/mpris/MediaPlayer2',arg0='org.mpris.MediaPlayer2.Player'"]
            )
        )
        self._bus.add_message_handler(self._on_message)

        # Set current playback state
        if self._current_player_name:
            metadata = await self._get_property(
                service=self._current_player_name,
                interface="org.mpris.MediaPlayer2.Player",
                property_name="Metadata"
            )
            shuffle: bool | None = await self._get_property(
                service=self._current_player_name,
                interface="org.mpris.MediaPlayer2.Player",
                property_name="Shuffle"
            )
            loop_status: str | None = await self._get_property(
                service=self._current_player_name,
                interface="org.mpris.MediaPlayer2.Player",
                property_name="LoopStatus"
            )
            volume: float | None = await self._get_property(
                service=self._current_player_name,
                interface="org.mpris.MediaPlayer2.Player",
                property_name="Volume"
            )
            artists_list = cast(list[str], (cast(dbus_next.signature.Variant, (metadata or {}).get("xesam:artist")) or {"value":None}).value)
            # Concatenate artists
            artists = ', '.join(artists_list) if artists_list else None

            self._last_state =  MediaPlaybackStateInner(
                        artist=artists or self._last_state.artist if self._last_state else None,
                        subtitle=cast(str, (cast(dbus_next.signature.Variant, (metadata or {}).get("xesam:album")) or {"value":None}).value),
                        title=cast(str, (cast(dbus_next.signature.Variant, (metadata or {}).get("xesam:title")) or {"value":None}).value),
                        is_shuffle_active=bool(shuffle) if shuffle is not None else None,
                        auto_repeat_mode=loop_status,
                        playback_status=status,
                        volume=int(volume * 100) if volume is not None else None
                    )
        else:
            log('debug', 'No MPRIS players found, setting default playback state.')
            self._last_state = default_media_playback_state()
            self._schedule_media_state_notification()

    def _on_message(self, msg: message.Message) -> message.Message | bool | None:
        if msg.message_type == MessageType.SIGNAL and msg.interface == "org.freedesktop.DBus.Properties" and msg.member == "PropertiesChanged":
            if msg.body[0] == "org.mpris.MediaPlayer2.Player":
                log('debug', f'Received D-Bus message: {msg.body}')
                changed_properties : dict[str, dbus_next.signature.Variant] = msg.body[1]
                if changed_properties:
                    if self._last_state is None:
                        self._last_state = default_media_playback_state()

                    if "PlaybackStatus" in changed_properties:
                        self._last_state.playback_status = changed_properties["PlaybackStatus"].value

                    if "Shuffle" in changed_properties:
                        shuffle: bool | None = changed_properties["Shuffle"].value
                        self._last_state.is_shuffle_active = bool(shuffle) if shuffle is not None else None

                    if "LoopStatus" in changed_properties:
                        loop_status: str | None = changed_properties["LoopStatus"].value
                        self._last_state.auto_repeat_mode = loop_status

                    if "Metadata" in changed_properties:
                        metadata: dict[str, dbus_next.signature.Variant] = changed_properties["Metadata"].value
                        artists_list = cast(list[str], (cast(dbus_next.signature.Variant, metadata.get("xesam:artist")) or {"value":None}).value)

                        # Concatenate artists
                        artists = ', '.join(artists_list) if artists_list else None

                        self._last_state.artist=artists
                        self._last_state.subtitle=cast(str, (cast(dbus_next.signature.Variant, metadata.get("xesam:album")) or {"value":None}).value)
                        self._last_state.title=cast(str, (cast(dbus_next.signature.Variant, metadata.get("xesam:title")) or {"value":None}).value)

                    if self.on_media_playback_info_changed:
                        self._schedule_media_state_notification()
                    return True
        return False

    def _schedule_media_state_notification(self):
        log('debug', 'Scheduling media state notification.')
        if self._notify_handle is not None:
            log('debug', 'Existing notification handle found, cancelling it before scheduling a new one.')
            self._notify_handle.cancel()

        self._notify_handle = self._loop.call_later(
            1,
            self._notify_media_state_changed
        )

    def _notify_media_state_changed(self):
        log('debug', '_notify_media_state_changed called.')
        self._notify_handle = None
        if self.on_media_playback_info_changed and self._last_state is not None:
            log('debug', 'Notifying media playback state change.')
            self.on_media_playback_info_changed(self._last_state)

    async def _get_property(
        self,
        service: str,
        interface: str,
        property_name: str
    ) -> Any | None:
        reply: Message | None = await self._bus.call(
            message.Message(
                destination=service,
                path="/org/mpris/MediaPlayer2",
                interface="org.freedesktop.DBus.Properties",
                member="Get",
                signature="ss",
                body=[
                    interface,
                    property_name
                ]
            )
        )
        if reply is None:
            log('error', f'Failed to retrieve property {property_name} from {service}.')
            return None
        if reply.message_type == MessageType.ERROR:
            log('error', f'Failed to retrieve property {property_name} from {service}. Error name: {reply.error_name}, Error: {reply.body[0]}')
            return None
        log('debug', f'Successfully retrieved property {property_name} from {service}. Value: {reply.body}')
        return reply.body[0].value;
    
    async def _call_player_method(
        self,
        service,
        method,
        signature="",
        body=None
    ):
        if body is None:
            body = []
        reply = await self._bus.call(
            message.Message(
                destination=service,
                path="/org/mpris/MediaPlayer2",
                interface="org.mpris.MediaPlayer2.Player",
                member=method,
                signature=signature,
                body=body
            )
        )
        if reply is None:
            log('error', f'Failed to call method {method} on {service}.')
            raise RuntimeError(f"Failed to call method {method} on {service}.")
        return reply.body

    @override
    def play(self) -> str:
        if self._current_player_name:
            retVal = asyncio.run_coroutine_threadsafe(self._call_player_method(
                service=self._current_player_name,
                method="Play"
            ), self._loop)
            log('debug', f'Play command sent to {self._current_player_name}, result: {retVal}')
            return "Success."
        return "Error: No player is set."

    @override
    def pause(self) -> str:
        if self._current_player_name:
            asyncio.run_coroutine_threadsafe(self._call_player_method(
                service=self._current_player_name,
                method="Pause"
            ), self._loop)
            return "Success."
        return "Error: No player is set."

    @override
    def stop(self) -> str:
        if self._current_player_name:
            asyncio.run_coroutine_threadsafe(self._call_player_method(
                service=self._current_player_name,
                method="Stop"
            ), self._loop)
            return "Success."
        return "Error: No player is set."

    @override
    def prev_track(self) -> str:
        if self._current_player_name:
            asyncio.run_coroutine_threadsafe(self._call_player_method(
                service=self._current_player_name,
                method="Previous"
            ), self._loop)
            return "Success."
        return "Error: No player is set."

    @override
    def next_track(self) -> str:
        if self._current_player_name:
            asyncio.run_coroutine_threadsafe(self._call_player_method(
                service=self._current_player_name,
                method="Next"
            ), self._loop)
            return "Success."
        return "Error: No player is set."

    @override
    def get_media_playback_state(self) -> MediaPlaybackStateInner:
        return self._last_state or default_media_playback_state()

    @override
    def cleanup(self):
        self._stop_event.set()
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2)
            self._loop.close()

    @override
    def start_playlist(self, path: str) -> str: return "Playlist functionality has not been implemented for MPRISController." # Not implemented at this time.
