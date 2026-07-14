from math import floor

from plugins.MediaPlayer.MediaControllerTypes import MediaPlaybackStateInner

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

        self._last_state: Optional[MediaPlaybackStateInner] = None
        self._current_player_name: str | None = None

    async def _init_player(self):
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
                    return
            except Exception:
                log('debug', f'Failed to get current playback status for {name}, continuing...')
                log('debug', f'Exception details: {sys.exc_info()[1]}')
                continue
        # fallback to first player found
        if mpris_names:
            log('debug', 'No active MPRIS player found, using the first available player.')
            self._current_player_name = mpris_names[0]
            if self._current_player_name:
                status = await self._get_property(
                    service=self._current_player_name,
                    interface="org.mpris.MediaPlayer2.Player",
                    property_name="PlaybackStatus"
                )

        # Add a message handler to listen for property changes
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
            artists_list = cast(list[str], (cast(dbus_next.signature.Variant, metadata.get("xesam:artist")) or {"value":None}).value)
            # Concatenate artists
            artists = ', '.join(artists_list) if artists_list else None

            self._last_state =  MediaPlaybackStateInner(
                        artist=artists or self._last_state.artist if self._last_state else None,
                        subtitle=cast(str, (cast(dbus_next.signature.Variant, metadata.get("xesam:album")) or {"value":None}).value),
                        title=cast(str, (cast(dbus_next.signature.Variant, metadata.get("xesam:title")) or {"value":None}).value),
                        is_shuffle_active=bool(shuffle) if shuffle is not None else None,
                        auto_repeat_mode=loop_status,
                        playback_status=status
                    )

    def _on_message(self, msg: message.Message) -> message.Message | bool | None:
        if msg.message_type == MessageType.SIGNAL and msg.interface == "org.freedesktop.DBus.Properties" and msg.member == "PropertiesChanged":
            if msg.body[0] == "org.mpris.MediaPlayer2.Player":
                changed_properties = msg.body[1]
                if changed_properties:
                    if self._last_state is None:
                        self._last_state = default_media_playback_state()

                    if "PlaybackStatus" in changed_properties:
                        self._last_state.playback_status = changed_properties["PlaybackStatus"].value

                    if "Metadata" in changed_properties:
                        metadata = changed_properties["Metadata"].value
                        shuffle: bool | None = None
                        loop_status: str | None = None
                        artists_list = cast(list[str], (cast(dbus_next.signature.Variant, metadata.get("xesam:artist")) or {"value":None}).value)

                        # Concatenate artists
                        artists = ', '.join(artists_list) if artists_list else None

                        self._last_state.artist=artists
                        self._last_state.subtitle=cast(str, (cast(dbus_next.signature.Variant, metadata.get("xesam:album")) or {"value":None}).value)
                        self._last_state.title=cast(str, (cast(dbus_next.signature.Variant, metadata.get("xesam:title")) or {"value":None}).value)
                        self._last_state.is_shuffle_active=bool(shuffle) if shuffle is not None else None
                        self._last_state.auto_repeat_mode=loop_status

                    if self.on_media_playback_info_changed:
                        self.on_media_playback_info_changed(self._last_state)
                    return True
        return False

    async def _get_property(
        self,
        service: str,
        interface: str,
        property_name: str
    ):
        reply = await self._bus.call(
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
            raise RuntimeError(f"Failed to retrieve property {property_name} from {service}.")
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
    def play(self) -> bool:
        if self._current_player_name:
            asyncio.run(self._call_player_method(
                service=self._current_player_name,
                method="Play"
            ))
            return True
        return False

    @override
    def pause(self) -> bool:
        if self._current_player_name:
            asyncio.run(self._call_player_method(
                service=self._current_player_name,
                method="Pause"
            ))
            return True
        return False

    @override
    def stop(self) -> bool:
        if self._current_player_name:
            asyncio.run(self._call_player_method(
                service=self._current_player_name,
                method="Stop"
            ))
            return True
        return False

    @override
    def prev_track(self) -> bool:
        if self._current_player_name:
            asyncio.run(self._call_player_method(
                service=self._current_player_name,
                method="Previous"
            ))
            return True
        return False

    @override
    def next_track(self) -> bool:
        if self._current_player_name:
            asyncio.run(self._call_player_method(
                service=self._current_player_name,
                method="Next"
            ))
            return True
        return False

    @override
    def get_media_playback_state(self) -> MediaPlaybackStateInner:
        return self._last_state or default_media_playback_state()

    @override
    def cleanup(self):
        pass
        # self._stop_event.set()
        # self._poll_thread.join(timeout=2)
        # self._loop.stop()
