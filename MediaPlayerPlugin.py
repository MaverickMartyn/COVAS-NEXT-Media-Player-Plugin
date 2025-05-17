from ast import Dict
import os
import platform
import subprocess
from typing import Any, Callable, Literal, TypedDict, cast, final, override
import asyncio
from openai.types.chat import ChatCompletionMessageParam
from winrt.windows.foundation import EventRegistrationToken
from winrt.windows.media.control import CurrentSessionChangedEventArgs, GlobalSystemMediaTransportControlsSession, GlobalSystemMediaTransportControlsSessionManager as MediaManager, GlobalSystemMediaTransportControlsSessionMediaProperties, PlaybackInfoChangedEventArgs

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from lib.Config import Config
from lib.PluginHelper import PluginHelper
from lib.PluginSettingDefinitions import PluginSettings, SettingsGrid, SelectOption, TextAreaSetting, TextSetting, SelectSetting, NumericalSetting, ToggleSetting, ParagraphSetting
from lib.ScreenReader import ScreenReader
from lib.Logger import log
from lib.EDKeys import EDKeys
from lib.EventManager import EventManager, Projection
from lib.ActionManager import ActionManager
from lib.PluginBase import PluginBase
from lib.SystemDatabase import SystemDatabase
from lib.Event import Event, StatusEvent

class MediaPlaybackState(TypedDict):
    event: str
    media_playback_state: Any

@dataclass
@final
class WMSAStateValueUpdatedEvent(Event):
    new_state: Any
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    kind: Literal['game', 'user', 'assistant', 'assistant_completed', 'tool', 'status', 'projected', 'external', 'archive'] = field(default='status')
    processed_at: float = field(default=0.0)

class CurrentMediaPlaybackState(Projection[MediaPlaybackState]):
    @override
    def get_default_state(self) -> MediaPlaybackState:
        return {
            'event': 'MediaState',
            'media_playback_state': {
                'artist': None,
                'subtitle': None,
                'title': None,
                'is_shuffle_active': False,
                'auto_repeat_mode': False,
                'playback_status': 'STOPPED'
            }
        }  # type: ignore

    @override
    def process(self, event: Event) -> None:
        if isinstance(event, WMSAStateValueUpdatedEvent):
            self.state['media_playback_state'] = event.new_state

# Main plugin class
# This is the class that will be loaded by the PluginManager.
class MediaPlayerPlugin(PluginBase):
    media_session_manager: MediaManager
    DEFAULT_PLAYBACK_METHOD: str = 'wmsa'
    current_session_changed_handler_registration_token: EventRegistrationToken | None = None
    playback_info_changed_handler_registration_token: EventRegistrationToken | None = None
    
    def __init__(self): # This is the name that will be shown in the UI.
        super().__init__(plugin_name = "Media Player", event_classes = [WMSAStateValueUpdatedEvent])

        self.media_session_manager = asyncio.run(self._initialize_media_session_manager())

        # Define the plugin settings
        # This is the settings that will be shown in the UI for this plugin.
        self.settings_config: PluginSettings | None = PluginSettings(
        key="MediaPlayerPlugin",
        label="Media Player Plugin",
        icon="music_note", # Uses Material Icons, like the built-in settings-tabs.
        grids=[
            SettingsGrid(
                key="general",
                label="General",
                fields=[
                    ParagraphSetting(
                        key="media_playback_method_description",
                        label="Media Playback Method",
                        type="paragraph",
                        readonly = False,
                        placeholder = None,
                        content="Select the media playback method you want to use. The default is Windows Media Session API, which is the most compatible with most media players.<br />"
                                + "Deeper integration with other media players are available.<br />"
                                + "If you want to use the media keys, select Media Keys. This will work with almost anything.<br />"
                                + "Note: Changing this setting will require restarting the assistant."
                    ),
                    SelectSetting(
                        key="media_playback_method",
                        label="Media Playback Method",
                        type="select",
                        readonly = False,
                        placeholder = None,
                        default_value = 'wmsa',
                        select_options= [
                            SelectOption(key="media_keys", label="Media Keys", value="media_keys", disabled=False),
                            SelectOption(key="wmsa", label="Windows Media Session API", value="wmsa", disabled=False),
                            SelectOption(key="mpv", label="MPV (NOT IMPLEMENTED)", value="mpv", disabled=True),
                            SelectOption(key="vlc", label="VLC (NOT IMPLEMENTED)", value="vlc", disabled=True),
                            SelectOption(key="spotify", label="Spotify (NOT IMPLEMENTED)", value="spotify", disabled=True),
                            SelectOption(key="soundcloud", label="SoundCloud (MAYBE IN THE FUTURE)", value="soundcloud", disabled=True),
                        ],
                        multi_select=False,
                    ),
                ]
            ),
        ]
    )
    
    @override
    def register_actions(self, helper: PluginHelper):
        # Register actions
        media_playback_method: str = cast(str, helper.get_plugin_settings('MediaPlayerPlugin', 'general', 'media_playback_method')) or self.DEFAULT_PLAYBACK_METHOD

        if media_playback_method == "media_keys":
            # Register media keys actions
            self.register_media_keys_actions(helper)
        elif media_playback_method == "wmsa":
            # Register Windows Media Session API actions
            self.register_wmsa_actions(helper)
        elif media_playback_method == "mpv":
            # Register MPV actions
            self.register_mpv_actions(helper)
        elif media_playback_method == "vlc":
            # Register VLC actions
            self.register_vlc_actions(helper)
        elif media_playback_method == "spotify":
            # Register Spotify actions
            self.register_spotify_actions(helper)
        else:
            log('error', f"Invalid media playback method: {media_playback_method}")
            return
            
        self.register_playlist_action(media_playback_method, helper)

        log('debug', f"Actions registered for {self.plugin_name}")
        
    @override
    def register_projections(self, helper: PluginHelper):
        # Register projections
        media_playback_method: str = cast(str, helper.get_plugin_settings('MediaPlayerPlugin', 'general', 'media_playback_method')) or self.DEFAULT_PLAYBACK_METHOD

        if media_playback_method == "media_keys":
            # Register media keys projections
            pass
        elif media_playback_method == "wmsa":
            # Register Windows Media Session API projections
            self.current_session_changed_handler_registration_token = self.media_session_manager.add_current_session_changed(lambda session, eventArgs: self.current_session_changed_handler(helper, session, eventArgs))
            helper.register_projection(CurrentMediaPlaybackState())
        elif media_playback_method == "mpv":
            # Register MPV projections
            pass
        elif media_playback_method == "vlc":
            # Register VLC projections
            pass
        elif media_playback_method == "spotify":
            # Register Spotify projections
            pass
        else:
            log('error', f"Invalid media playback method: {media_playback_method}")
            return
            
        self.register_playlist_action(media_playback_method, helper)

        log('debug', f"Projections registered for {self.plugin_name}")

    @override
    def register_sideeffects(self, helper: PluginHelper):
        pass # Unused for now

    @override
    def register_prompt_event_handlers(self, helper: PluginHelper):
        pass # Unused for now
        
    @override
    def register_status_generators(self, helper: PluginHelper):
        # Register prompt generators
        helper.register_status_generator(self.media_player_state_status_generator)
        
    
    @override
    def on_chat_stop(self, helper: PluginHelper):
        # Executed when the chat is stopped
        if self.current_session_changed_handler_registration_token is not None:
            self.media_session_manager.remove_current_session_changed(self.current_session_changed_handler_registration_token)
        log('debug', f"Executed on_chat_stop hook for {self.plugin_name}")

    # Actions
    def pressMediaKey(self, args, projected_states, helper: PluginHelper) -> str:
        log('info', 'pressing media key: ', args)
        key: str | None = args['key']
        if key is None:
            return "Error: No key specified."
        if key == "play_pause":
            helper.send_key('MediaPlayPause')
        elif key == "next":
            helper.send_key('MediaNextTrack')
        elif key == "previous":
            helper.send_key('MediaPreviousTrack')
        elif key == "stop":
            helper.send_key('MediaStop')
        else:
            return "Error: Invalid key specified."
            
        return "Pressed media key: " + key
    def wmsa_action(self, args, projected_states, helper: PluginHelper) -> str:
        log('info', 'Activating Windows Media Session API action: ', args)
        action: str | None = args['action']
        if action is None:
            return "Error: No action specified."

        success: bool = False
        if action == "play":
            success = asyncio.run(self.wmsa_play())
        elif action == "pause":
            success = asyncio.run(self.wmsa_pause())
        elif action == "next":
            success = asyncio.run(self.wmsa_skip_next())
        elif action == "previous":
            success = asyncio.run(self.wmsa_skip_previous())
        elif action == "stop":
            success = asyncio.run(self.wmsa_stop())
        else:
            return "Error: Invalid action specified."

        if not success:
            return "Error: Failed to activate Windows Media Session API action: " + action
            
        return "Activated Windows Media Session API action: " + action

    def current_session_changed_handler(self, helper: PluginHelper, session: MediaManager, eventArgs: CurrentSessionChangedEventArgs):
        current_session = session.get_current_session()
        if self.playback_info_changed_handler_registration_token is not None:
            for running_session in session.get_sessions():
                running_session.remove_playback_info_changed(self.playback_info_changed_handler_registration_token)
        self.playback_info_changed_handler_registration_token = current_session.add_playback_info_changed(lambda session, eventArgs: self.playback_info_changed_handler(helper, session, eventArgs))

        log('info', 'Session changed: ', session)
        self.set_wmsa_state(helper, current_session)

    def playback_info_changed_handler(self, helper: PluginHelper, session: GlobalSystemMediaTransportControlsSession, eventArgs: PlaybackInfoChangedEventArgs):
        log('info', 'Playback info changed: ', session)
        self.set_wmsa_state(helper, session)

    async def wmsa_get_media_properties(self, session: GlobalSystemMediaTransportControlsSession) -> GlobalSystemMediaTransportControlsSessionMediaProperties | None:
        # log('debug', 'MediaManager: ', session)
        # curr_session = session.get_current_session()
        # log('debug', 'Current session: ', curr_session)
        return await session.try_get_media_properties_async()

    async def wmsa_play(self) -> bool:
        return await self.media_session_manager.get_current_session().try_play_async()

    async def wmsa_pause(self) -> bool:
        return await self.media_session_manager.get_current_session().try_pause_async()

    async def wmsa_skip_next(self) -> bool:
        return await self.media_session_manager.get_current_session().try_skip_next_async()

    async def wmsa_skip_previous(self) -> bool:
        return await self.media_session_manager.get_current_session().try_skip_previous_async()

    async def wmsa_stop(self) -> bool:
        ret_val = await self.media_session_manager.get_current_session().try_stop_async()
        if ret_val:
            ret_val = await self.media_session_manager.get_current_session().try_pause_async()
        return ret_val


    # Functions
    def set_wmsa_state(self, helper: PluginHelper, current_session: GlobalSystemMediaTransportControlsSession):
        playback_info = current_session.get_playback_info()
        media_properties = asyncio.run(self.wmsa_get_media_properties(current_session))
        if media_properties is None:
            return
        state: dict[str, str|bool] = {
            # 'album_artist': media_properties.album_artist,
            # 'album_title': media_properties.album_title,
            # 'album_track_count': media_properties.album_track_count,
            'artist': media_properties.artist,
            # 'genres': cast(list[str], media_properties.genres),
            # 'playback_type': media_properties.playback_type, # Not available, despite typings
            'subtitle': media_properties.subtitle,
            # 'thumbnail': media_properties.thumbnail,
            'title': media_properties.title,
            # 'track_number': media_properties.track_number,
            }
        if hasattr(playback_info, 'is_shuffle_active'):
            state['is_shuffle_active'] = playback_info.is_shuffle_active or False
        if hasattr(playback_info, 'auto_repeat_mode'):
            state['auto_repeat_mode'] = playback_info.auto_repeat_mode or False
        if hasattr(playback_info, 'playback_status'):
            state['playback_status'] = playback_info.playback_status.name
            
        log('info', 'Current state: ', state)
        
        event = WMSAStateValueUpdatedEvent(state)
        helper.put_incoming_event(event) # Updates the projected state

    def register_media_keys_actions(self, helper: PluginHelper):
        # Register keybindings
        helper.register_keybindings({
            'MediaPlayPause': { 'key': 162, 'mods': [], 'hold': False },
            'MediaPreviousTrack': { 'key': 144, 'mods': [], 'hold': False },
            'MediaNextTrack': { 'key': 153, 'mods': [], 'hold': False },
            'MediaStop': { 'key': 164, 'mods': [], 'hold': False }
        })

        # Register media keys actions
        helper.register_action('press_media_key', "Media/Music control. Play/pause/next/previous/stop", {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "enum": ["play_pause", "next", "previous", "stop"],
                    "description": "The media key to press."
                }
            }
        }, lambda args, projected_states: self.pressMediaKey(args, projected_states, helper), 'global')

    def register_wmsa_actions(self, helper: PluginHelper):
        # Register Windows Media Session API actions
        # Use https://pypi.org/project/pywmsa/

        helper.register_action('media_player_action', "Media/Music control. Play/pause/next/previous/stop", {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play', 'pause", "next", "previous", "stop"],
                    "description": "The media player function."
                }
            }
        }, lambda args, projected_states: self.wmsa_action(args, projected_states, helper), 'global')

    def register_mpv_actions(self, helper: PluginHelper):
        # Register MPV media player actions
        # Use https://pypi.org/project/mpv-python/
        pass

    def register_vlc_actions(self, helper: PluginHelper):
        # Register VLC media player actions
        # Use https://pypi.org/project/python-vlc/
        pass

    def register_spotify_actions(self, helper: PluginHelper):
        # Register Spotify media player actions
        # Use https://pypi.org/project/pyspotify/
        pass

    def register_playlist_action(self, media_playback_method: str, helper: PluginHelper):
        # Register playlist action
        # Find all playlist files
        files = os.listdir('./plugins/MediaPlayer/playlists')
        files = list(filter(lambda x: x.endswith('.m3u'), files))
        playlist_names = list(map(lambda x: x[:-4], files))
        log('debug', f"Discovered playlist names: {playlist_names}")

        helper.register_action('start_playlist', "Start a music/media playlist by name", {
            "type": "object",
            "properties": {
                "playlist": {
                    "type": "string",
                    "enum": playlist_names,
                    "description": "The playlist to start playing."
                }
            }
        }, lambda args, projected_states: self.start_playlist(args, projected_states, media_playback_method, helper), 'global')

    def start_playlist(self, args, projected_states, media_playback_method: str, helper: PluginHelper) -> str:
        if media_playback_method == "media_keys":
            # Start playlist using media keys
            pass
        elif media_playback_method == "wmsa":
            # Start playlist using Windows Media Session API
            pass
        elif media_playback_method == "mpv":
            # Start playlist using MPV
            pass
        elif media_playback_method == "vlc":
            # Start playlist using VLC
            pass
        elif media_playback_method == "spotify":
            # Start playlist using Spotify
            pass
        else:
            log('error', f"Invalid media playback method: {media_playback_method}")
            return "Error: Invalid media playback method."

        # Temporary catch-all.
        # TODO: Expand this to support other media players
        log('info', f"Current directory: {os.getcwd()}")
        playlist_path: str = os.path.join(os.getcwd(), 'plugins', 'MediaPlayer', 'playlists', f'{args["playlist"]}.m3u')
        log('info', f"Playlist path: {playlist_path}")
        log('info', f'Playlist file exists: {os.path.exists(playlist_path)}')
        if platform.system() == 'Darwin':       # macOS
            subprocess.call(('open', playlist_path))
        elif platform.system() == 'Windows':    # Windows
            os.startfile(playlist_path)
        else:                                   # linux variants
            subprocess.call(('xdg-open', playlist_path))

        return 'Started playlist: ' + args['playlist']

    async def get_media_info(self):
        current_session = self.media_session_manager.get_current_session()
        if current_session:
            info = await current_session.try_get_media_properties_async()
            if info is None:
                return
            print(f"Now Playing: {info.title} by {info.artist}")

    # asyncio.run(get_media_info())

    async def _initialize_media_session_manager(self):
        return await MediaManager.request_async()

    def media_player_state_status_generator(self, projected_states: dict[str, dict]) -> list[tuple[str, Any]]:
        return [
            ('Current media player state', projected_states['CurrentMediaPlayerState']['state'])
        ]
        