import os
import platform
import random
import subprocess
from typing import Any, Callable, Literal, TypedDict, cast, final, override

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from openai.types.chat import ChatCompletionMessageParam

from lib.PluginHelper import PluginHelper, PluginManifest
from lib.PluginSettingDefinitions import PluginSettings, SettingsGrid, SelectOption, TextAreaSetting, TextSetting, SelectSetting, NumericalSetting, ToggleSetting, ParagraphSetting
from lib.Logger import log
from lib.EventManager import Projection
from lib.PluginBase import PluginBase
from lib.Event import Event, ProjectedEvent
from .MediaControllerTypes import MediaPlaybackStateInner, default_media_playback_state, MediaControllerBase
from .MediaControllers import get_platform_controller

@dataclass
@final
class MediaPlaybackStateChangedEvent(Event):
    new_state: MediaPlaybackStateInner
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    kind: Literal['game', 'user', 'assistant', 'assistant_completed', 'tool', 'status', 'projected', 'external', 'archive'] = field(default='tool')
    processed_at: float = field(default=0.0)
    processed_by_us_at: float = field(default=0.0)
    
class MediaPlaybackState(TypedDict):
    event: str
    media_playback_state: MediaPlaybackStateInner

class CurrentMediaPlaybackState(Projection[MediaPlaybackState]):
    @override
    def get_default_state(self) -> MediaPlaybackState:
        return MediaPlaybackState({
            'event': 'MediaState',
            'media_playback_state': default_media_playback_state()
        })

    @override
    def process(self, event: Event) -> list[ProjectedEvent]:
        projected_events: list[ProjectedEvent] = []
        if isinstance(event, MediaPlaybackStateChangedEvent):
            self.state['media_playback_state'] = event.new_state
            projected_events.append(ProjectedEvent({"event": "MediaPlaybackStateChanged", "new_state": event.new_state}))
        return projected_events

# Main plugin class
# This is the class that will be loaded by the PluginManager.
class MediaPlayerPlugin(PluginBase):
    DEFAULT_PLAYBACK_METHOD: str = 'system_wide' if platform.system() in ['Windows', 'Linux'] else 'media_keys'
    DEFAULT_MEDIA_CHANGE_COMMENT_CHANCE : int = 10
    
    def __init__(self, plugin_manifest: PluginManifest): # This is the name that will be shown in the UI.
        super().__init__(plugin_manifest, event_classes = [MediaPlaybackStateChangedEvent])

        self._media_controller: MediaControllerBase | None = None

        # Define the plugin settings
        # This is the settings that will be shown in the UI for this plugin.
        os_name = platform.system()
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
                            content="Select the media playback method you want to use. The default is the Generic System-Wide Integration, which is the most compatible with most media players.<br />"
                                    + "The system-wide integration uses native APIs, depending on the platform, to query emdia information and control playback.<br />"
                                    + "Deeper integration with other media players are available.<br />"
                                    + "If you want to use the media keys, select Media Keys. This will work with almost anything, but provides no media meta data.<br />"
                                    + "Note: Changing this setting will require restarting the assistant."
                        ),
                        SelectSetting(
                            key="media_playback_method",
                            label="Media Playback Method",
                            type="select",
                            readonly = False,
                            placeholder = None,
                            default_value = self.DEFAULT_PLAYBACK_METHOD,
                            select_options= [
                                SelectOption(key="media_keys", label="Media Keys", value="media_keys", disabled=False),
                                SelectOption(key="system_wide", label="Generic System-Wide Integration", value="system_wide", disabled=os_name != 'Windows' and os_name != 'Linux'),
                                SelectOption(key="mpv", label="MPV (NOT IMPLEMENTED)", value="mpv", disabled=True),
                                SelectOption(key="vlc", label="VLC (NOT IMPLEMENTED)", value="vlc", disabled=True),
                                SelectOption(key="spotify", label="Spotify (NOT IMPLEMENTED)", value="spotify", disabled=True),
                                SelectOption(key="soundcloud", label="SoundCloud (MAYBE IN THE FUTURE)", value="soundcloud", disabled=True),
                            ],
                            multi_select=False,
                        ),
                        ParagraphSetting(
                            key="media_change_assistant_comments_description",
                            label="Assistant Comments (Only available for Generic System-Wide Integration)",
                            type="paragraph",
                            readonly = False,
                            placeholder = None,
                            content="When the media playback changes the assistant may comment, based on the chance set below (in percent).<br />" +
                                    "Default is 10%. Set to 0 to disable."
                        ),
                        NumericalSetting(
                            key="media_change_assistant_comments_chance",
                            label="Assistant Comments Chance (In percent)",
                            type="number",
                            readonly = False,
                            placeholder = None,
                            default_value = self.DEFAULT_MEDIA_CHANGE_COMMENT_CHANCE,
                            min_value = 0,
                            max_value = 100,
                            step = 1
                        ),
                    ]
                ),
            ]
        )
    
    @override
    def register_actions(self, helper: PluginHelper):
        # Register actions
        media_playback_method = self._get_media_playback_method(helper)

        if media_playback_method == "media_keys":
            # Register media keys actions
            self.register_media_keys_actions(helper)
        elif media_playback_method == "system_wide":
            # Register actions for the generic system-wide integration
            self.register_system_wide_media_actions(helper)
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

        log('debug', f"Actions registered for {self.plugin_manifest.name}")
        
    @override
    def register_projections(self, helper: PluginHelper):
        # Register projections
        media_playback_method = self._get_media_playback_method(helper)

        if media_playback_method == "media_keys":
            # Register media keys projections
            pass
        elif media_playback_method == "system_wide":
            # Register the generic media meta data projection
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

        log('debug', f"Projections registered for {self.plugin_manifest.name}")

    @override
    def register_sideeffects(self, helper: PluginHelper):
        pass

    @override
    def register_prompt_event_handlers(self, helper: PluginHelper):
        pass # helper.register_prompt_event_handler(lambda event: self.new_media_event_prompt_handler(event, helper)),
        
    @override
    def register_status_generators(self, helper: PluginHelper):
        # Register prompt generators
        helper.register_status_generator(lambda projected_states: self.media_player_state_status_generator(helper, projected_states))
    
    @override
    def on_plugin_helper_ready(self, helper: PluginHelper):
        if self._get_media_playback_method(helper) == "system_wide":
            self._media_controller = get_platform_controller()
            self._media_controller_on_media_playback_info_changed_handler(helper, self._media_controller.get_media_playback_state())
            self._media_controller.on_media_playback_info_changed = lambda state: self._media_controller_on_media_playback_info_changed_handler(helper, state)
        
    @override
    def on_chat_stop(self, helper: PluginHelper):
        # Executed when the chat is stopped
        if self._get_media_playback_method(helper) == "system_wide":
            if self._media_controller is not None:
                self._media_controller.cleanup()  # Cleanup the media controller
                self._media_controller = None  # Reset the media controller
        log('debug', f"Executed on_chat_stop hook for {self.plugin_manifest.name}")

    @override
    def register_should_reply_handlers(self, helper: PluginHelper):
        if self._get_media_playback_method(helper) == "system_wide":
            helper.register_should_reply_handler(lambda event, projected_states: self.media_player_should_reply_handler(helper, event, projected_states))

    # Actions
    def pressMediaKey(self, args, projected_states, helper: PluginHelper) -> str:
        log('debug', 'pressing media key: ', args)
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
    def system_wide_media_action(self, args, projected_states, helper: PluginHelper) -> str:
        log('debug', 'Activating Generic Media API action: ', args)
        action: str | None = args['action']
        if action is None:
            return "Error: No action specified."

        if self._media_controller is None:
            return "Error: Media controller is not initialized, despite using generic media integration. This should not happen."

        success: bool = False
        if action == "play":
            success = self._media_controller.play()
        elif action == "pause":
            success = self._media_controller.pause()
        elif action == "next":
            success = self._media_controller.next_track()
        elif action == "previous":
            success = self._media_controller.prev_track()
        elif action == "stop":
            success = self._media_controller.stop()
        else:
            return "Error: Invalid action specified."

        if not success:
            return "Error: Failed to activate Windows Media Session API action: " + action
            
        return "Activated Windows Media Session API action: " + action

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

    def register_system_wide_media_actions(self, helper: PluginHelper):
        # Register system-wide media actions

        helper.register_action('media_player_action', "Media/Music control. Play/pause/next/previous/stop", {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play', 'pause", "next", "previous", "stop"],
                    "description": "The media player function."
                }
            }
        }, lambda args, projected_states: self.system_wide_media_action(args, projected_states, helper), 'global')

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
        playlists_path = os.path.join(helper.get_plugin_data_path(self.plugin_manifest), './playlists')
        if not os.path.exists(playlists_path):
            os.makedirs(playlists_path)

        files = os.listdir(playlists_path)
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
        elif media_playback_method == "system_wide":
            # Start playlist using the default media player
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
        log('debug', f"Current directory: {os.getcwd()}")
        playlist_path: str = os.path.join(helper.get_plugin_data_path(self.plugin_manifest), 'playlists', f'{args["playlist"]}.m3u')
        log('debug', f"Playlist path: {playlist_path}")
        log('debug', f'Playlist file exists: {os.path.exists(playlist_path)}')
        if platform.system() == 'Darwin':       # macOS
            subprocess.call(('open', playlist_path))
        elif platform.system() == 'Windows':    # Windows
            os.startfile(playlist_path)
        else:                                   # linux variants
            subprocess.call(('xdg-open', playlist_path))

        return 'Started playlist: ' + args['playlist']

    def media_player_state_status_generator(self, helper: PluginHelper, projected_states: dict[str, dict]) -> list[tuple[str, Any]]:
        media_playback_method = self._get_media_playback_method(helper)
        if media_playback_method != "system_wide":
            log('debug', f'Media playback method is not system_wide ({media_playback_method}), skipping media player state status generation.')
            return []
        state = projected_states.get('CurrentMediaPlaybackState', {}).get('media_playback_state', {})
        log('debug', f'Adding state to context: {state}')
        return [
            ('Current media player state', state)
        ]

    def media_player_should_reply_handler(self, helper: PluginHelper, event: Event, projected_states: dict[str, dict]) -> bool | None:
        if isinstance(event, MediaPlaybackStateChangedEvent):
            if event.processed_by_us_at == 0.0: # Only handle unprocessed events, of type MediaPlaybackStateChangedEvent.
                # Decide based on chance set in media_change_assistant_comments_chance setting.
                event.processed_by_us_at = datetime.now(timezone.utc).timestamp() # Mark the event as processed by this plugin.
                chance = cast(int, helper.get_plugin_settings('MediaPlayerPlugin', 'general', 'media_change_assistant_comments_chance') or self.DEFAULT_MEDIA_CHANGE_COMMENT_CHANCE)
                if chance == 0:
                    return False
                if (random.random() * 100) < chance:
                    return True
                return False
        return None # No opinion. Let the AI decide.
    
    def _media_controller_on_media_playback_info_changed_handler(self, helper: PluginHelper, state: MediaPlaybackStateInner):
        log('debug', 'New media state: ', state)
        
        event = MediaPlaybackStateChangedEvent(state)
        helper.put_incoming_event(event) # Updates the projected state

    def _get_media_playback_method(self, helper: PluginHelper) -> str:
        return cast(str, helper.get_plugin_settings('MediaPlayerPlugin', 'general', 'media_playback_method')) or self.DEFAULT_PLAYBACK_METHOD
    
    def new_media_event_prompt_handler(self, event: Event, helper: PluginHelper) -> list[ChatCompletionMessageParam]:
        if isinstance(event, MediaPlaybackStateChangedEvent):
            log('debug', f'New media event: {event}')
            # Create a message for the assistant
            return [
                {
                    "role": "system",
                    "content": f"New media playback state: {event.new_state}",
                }
            ]
        return []
    