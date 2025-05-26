from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, TypedDict, final, override

from lib.Event import Event
from lib.EventManager import Projection
from lib.PluginHelper import PluginHelper
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

class MediaController(ABC):
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

class MPRISController(MediaController):
    # Linux backend
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

class WindowsMediaController(MediaController):
    # Windows backend
    from winrt.windows.foundation import EventRegistrationToken
    from winrt.windows.media.control import CurrentSessionChangedEventArgs, PlaybackInfoChangedEventArgs, GlobalSystemMediaTransportControlsSession, GlobalSystemMediaTransportControlsSessionMediaProperties, GlobalSystemMediaTransportControlsSessionManager as MediaManager
    
    current_session: GlobalSystemMediaTransportControlsSession | None = None
    current_session_changed_token: EventRegistrationToken | None = None
    playback_info_changed_token: EventRegistrationToken | None = None
    media_session_manager: MediaManager
    last_media_playback_state: MediaPlaybackStateInner = field(default_factory=default_media_playback_state)

    def __init__(self):
        super().__init__()

        self.media_session_manager = asyncio.run(self._initialize_media_session_manager())

        # Initialize the current session and add event handlers
        self.current_session = self.media_session_manager.get_current_session()
        self.current_session_changed_token = self.media_session_manager.add_current_session_changed(self.current_session_changed_handler)

        if  self.current_session is not None:
            self.playback_info_changed_token = self.current_session.add_playback_info_changed(lambda sender, event: self.playback_info_changed_handler())
    
    @override
    def play(self): return asyncio.run(self._inner_play())

    @override
    def pause(self): return asyncio.run(self._inner_pause())

    @override
    def stop(self): return asyncio.run(self._inner_stop())

    @override
    def prev_track(self): return asyncio.run(self._inner_prev_track())

    @override
    def next_track(self): return asyncio.run(self._inner_next_track())

    @override
    def get_media_playback_state(self) -> MediaPlaybackStateInner: return self.get_wmsa_state()

    @override
    def cleanup(self):
        if self.playback_info_changed_token is not None:
            if self.current_session is not None:
                self.current_session.remove_playback_info_changed(self.playback_info_changed_token)
            self.media_session_manager.get_current_session().remove_playback_info_changed(self.playback_info_changed_token)
            self.playback_info_changed_token = None
        if self.current_session_changed_token is not None:
            self.media_session_manager.remove_current_session_changed(self.current_session_changed_token)
            self.current_session_changed_token = None

    async def _inner_play(self) -> bool:
        return await self.media_session_manager.get_current_session().try_play_async()

    async def _inner_pause(self) -> bool:
        return await self.media_session_manager.get_current_session().try_pause_async()

    async def _inner_prev_track(self) -> bool:
        return await self.media_session_manager.get_current_session().try_skip_previous_async()

    async def _inner_next_track(self) -> bool:
        return await self.media_session_manager.get_current_session().try_skip_next_async()

    async def _inner_stop(self) -> bool:
        ret_val = await self.media_session_manager.get_current_session().try_stop_async()
        if ret_val:
            ret_val = await self.media_session_manager.get_current_session().try_pause_async()
        return ret_val

    async def wmsa_get_media_properties(self, session: GlobalSystemMediaTransportControlsSession) -> GlobalSystemMediaTransportControlsSessionMediaProperties | None:
        # log('debug', 'MediaManager: ', session)
        # curr_session = session.get_current_session()
        # log('debug', 'Current session: ', curr_session)
        return await session.try_get_media_properties_async()

    def current_session_changed_handler(self, sender: MediaManager, args: CurrentSessionChangedEventArgs):
        log('debug', 'Current session changed handler called.')
        new_session = self.media_session_manager.get_current_session()
        if new_session == self.current_session:
            log('debug', 'Current session did not change.')
            return
            
        if self.playback_info_changed_token:
            if self.current_session is not None:
                self.current_session.remove_playback_info_changed(self.playback_info_changed_token)
            self.playback_info_changed_token = None

        # Update the current session
        self.current_session = new_session
        
        if self.current_session is not None:
            self.playback_info_changed_token = self.current_session.add_playback_info_changed(lambda sender, event: self.playback_info_changed_handler())
            self.playback_info_changed_handler()

    def playback_info_changed_handler(self):
        log('debug', 'Playback info changed handler called.')
        state = self.get_wmsa_state()

        if self.last_media_playback_state == state:
            log('debug', 'Playback state did not change, skipping notification.')
            return
        self.last_media_playback_state = state

        if self.on_media_playback_info_changed is not None:
            self.on_media_playback_info_changed(state)
    
    def get_wmsa_state(self) -> MediaPlaybackStateInner:
        if self.current_session is None:
            log('debug', 'Current media session is None, cannot set state.')
            return default_media_playback_state()
        playback_info = self.current_session.get_playback_info()
        media_properties = asyncio.run(self.wmsa_get_media_properties(self.current_session))
        if media_properties is None:
            return default_media_playback_state()
        state = MediaPlaybackStateInner({
            'artist': media_properties.artist,
            'subtitle': media_properties.subtitle,
            'title': media_properties.title,
            'is_shuffle_active': False,
            'auto_repeat_mode': False,
            'playback_status': None
            })
        if hasattr(playback_info, 'is_shuffle_active'):
            state['is_shuffle_active'] = playback_info.is_shuffle_active or False
        if hasattr(playback_info, 'auto_repeat_mode'):
            state['auto_repeat_mode'] = playback_info.auto_repeat_mode or False
        if hasattr(playback_info, 'playback_status'):
            state['playback_status'] = playback_info.playback_status.name
        
        return state

    async def _initialize_media_session_manager(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
        return await MediaManager.request_async()

class MacOSMediaController(MediaController):
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

def get_platform_controller() -> MPRISController | WindowsMediaController | MacOSMediaController:
    import platform
    os_name = platform.system()
    if os_name == "Linux":
        return MPRISController()
    elif os_name == "Windows":
        return WindowsMediaController()
    elif os_name == "Darwin":
        return MacOSMediaController()
    else:
        log('error', f'Unsupported platform: {os_name}')
        raise NotImplementedError(f'MediaController not implemented for {os_name}')
