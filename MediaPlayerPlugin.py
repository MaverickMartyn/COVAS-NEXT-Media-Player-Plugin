from datetime import datetime, timezone
import os
import platform
import random
import subprocess
from typing import Any, Literal, TypeVar, cast, override

from pydantic import BaseModel, Field

from lib.PluginHelper import PluginEvent, PluginHelper, ProjectedStates
from lib.PluginSettingDefinitions import (
    PluginSettings, SettingsGrid, SelectOption, TextAreaSetting, TextSetting, SelectSetting, NumericalSetting, ToggleSetting, ParagraphSetting
)
from lib.Logger import log
from lib.PluginBase import PluginBase, PluginManifest
from .Projections.CurrentMediaPlaybackState import CurrentMediaPlaybackState
from .ActionParams.MediaPlayerActionParams import MediaPlayerActionParams
from .ActionParams.PressMediaKeyParams import PressMediaKeyParams
from .ActionParams.StartPlaylistParams import StartPlaylistParams
from .MediaControllerTypes import MediaControllerBase, MediaPlaybackStateInner
from .MediaControllers import get_platform_controller

# Main plugin class
# This is the class that will be loaded by the PluginManager.
class MediaPlayerPlugin(PluginBase):
    DEFAULT_PLAYBACK_METHOD: str = 'system_wide' if platform.system() in ['Windows', 'Linux'] else 'media_keys'
    DEFAULT_MEDIA_CHANGE_COMMENT_CHANCE : int = 10

    def __init__(self, plugin_manifest: PluginManifest):
        super().__init__(plugin_manifest)

        self._media_controller: MediaControllerBase | None = None
        self._playback_state_projection: CurrentMediaPlaybackState | None = None
        os_name = platform.system()

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
    
    # The following overrides are optional. Remove them if you don't need them.
    @override
    def on_chat_start(self, helper: PluginHelper):
        media_playback_method = self.get_setting("media_playback_method", self.DEFAULT_PLAYBACK_METHOD, str)

        # Register actions
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
            
        self.register_playlist_action(helper)
        
        log('debug', f"Actions registered for {self.plugin_manifest.name}")

        # Register events
        if media_playback_method == "system_wide":
            helper.register_event('MediaPlaybackStateChangedEvent', should_reply_check=self.media_player_should_reply_handler, prompt_generator=self.new_media_event_prompt_handler)
            log('debug', 'Registered media playback state changed event.')
        
        log('debug', f"Events registered for {self.plugin_manifest.name}")

        # Register projections
        if media_playback_method == "system_wide":
            self._playback_state_projection = CurrentMediaPlaybackState()
            helper.register_projection(self._playback_state_projection)
            
        # Register status generators
        if media_playback_method == "system_wide":
            helper.register_status_generator(self.media_player_state_status_generator)
            #lambda states: [("DemoProjectionValue", "The current demosaicing value is " + str(states.get("DemoProjection").value) if states.get("DemoProjection") else None)]

        if media_playback_method == "system_wide":
            self._media_controller = get_platform_controller()
            projection = self._playback_state_projection
            if projection is not None:
                current_state = self._media_controller.get_media_playback_state()
                log('debug', f"Found previous track info on startup")
                if projection.state != current_state:
                    self._media_controller_on_media_playback_info_changed_handler(helper, current_state)
                    log('debug', f"Updated current track on startup")
            
            self._media_controller.on_media_playback_info_changed = lambda state: self._media_controller_on_media_playback_info_changed_handler(helper, state)
            log('debug', f"Media controller initialized{self.plugin_manifest.name}")

        pass
    
    @override
    def on_chat_stop(self, helper: PluginHelper):
        # Executed when the chat is stopped
        pass
    
    def _media_controller_on_media_playback_info_changed_handler(self, helper: PluginHelper, state: MediaPlaybackStateInner):
        log('debug', 'New media state from controller: ', state)
        
        event = PluginEvent(
            plugin_event_name="MediaPlaybackStateChangedEvent",
            plugin_event_content=state.model_dump()
        )
        helper.dispatch_event(event) # Updates the projected state

    def new_media_event_prompt_handler(self, event: PluginEvent) -> str:
        log('debug', f'New media event: {event}')
        if (event.plugin_event_name == "MediaPlaybackStateChangedEvent"):
            raise ValueError("This prompt handler is only for media playback state changed events.")
        log('debug', f'New media event: {event}')
        # Create a message for the assistant
        # Does this need to be transformed to JSON, or does that happen automagically?
        return f"New media playback state: {event.plugin_event_content}"
            

    def media_player_should_reply_handler(self, event: PluginEvent) -> bool:
        log('debug', 'new_media_event_prompt_handler triggered', event)
        if event.plugin_event_name != 'MediaPlaybackStateChangedEvent':
            raise ValueError("This should_reply handler is only for media playback state changed events.")

        # Check if event.timestamp is within the last 5 seconds, mostly to avoid commenting on chat startup.
        if datetime.now(timezone.utc).timestamp() - event.processed_at <= 5:
            # Decide based on chance set in media_change_assistant_comments_chance setting.
            chance = self.get_setting("media_change_assistant_comments_chance", self.DEFAULT_MEDIA_CHANGE_COMMENT_CHANCE, int)
            if chance == 0:
                return False
            if (random.random() * 100) < chance:
                return True
            return False
        return False

    # Actions
    def pressMediaKey(self, args: PressMediaKeyParams, helper: PluginHelper) -> str:
        log('debug', 'pressing media key: ', args)
        key: str | None = args.key
        # if key is None:
        #     return "Error: No key specified."
        if key == "play_pause":
            helper.send_key('MediaPlayPause')
        elif key == "next":
            helper.send_key('MediaNextTrack')
        elif key == "previous":
            helper.send_key('MediaPreviousTrack')
        elif key == "stop":
            helper.send_key('MediaStop')
        # else:
        #     return "Error: Invalid key specified."
            
        return "Pressed media key: " + key

    def media_player_state_status_generator(self, projected_states: ProjectedStates) -> list[tuple[str, Any]]:
        media_playback_method = self.get_setting("media_playback_method", self.DEFAULT_PLAYBACK_METHOD, str)
        if media_playback_method != "system_wide":
            log('debug', f'Media playback method is not system_wide ({media_playback_method}), skipping media player state status generation.')
            return []
        state = projected_states.get('CurrentMediaPlaybackState', None)
        log('debug', f'Adding state to context: {state}')
        return [
            ('Current media player state', state.model_dump() if state else None)
        ]

    def system_wide_media_action(self, args: MediaPlayerActionParams, projected_states: ProjectedStates) -> str:
        log('debug', 'Activating Generic Media API action: ', args)

        if self._media_controller is None:
            return "Error: Media controller is not initialized, despite using generic media integration. This should not happen."

        success: bool = False
        if args.action == "play":
            success = self._media_controller.play()
        elif args.action == "pause":
            success = self._media_controller.pause()
        elif args.action == "next":
            success = self._media_controller.next_track()
        elif args.action == "previous":
            success = self._media_controller.prev_track()
        elif args.action == "stop":
            success = self._media_controller.stop()
        else:
            return "Error: Invalid action specified."

        if not success:
            return "Error: Failed to activate Windows Media Session API action: " + args.action
            
        return "Activated Windows Media Session API action: " + args.action

    def register_media_keys_actions(self, helper: PluginHelper):
        # Register keybindings
        # TODO: We're only directly updating the key dictionary here, because of an API regression. Change to a public API when one is available.
        # The new solution might be a new sendley API that accepts OS-agnostic key names, rather than having to inject new keys to the internal game-specific key dictionary.
        helper._keys.keys.update({
            'MediaPlayPause': { 'key': 162, 'mods': [], 'hold': False },
            'MediaPreviousTrack': { 'key': 144, 'mods': [], 'hold': False },
            'MediaNextTrack': { 'key': 153, 'mods': [], 'hold': False },
            'MediaStop': { 'key': 164, 'mods': [], 'hold': False }
        })

        # Register media keys actions
        helper.register_action(
            'press_media_key',
            "Media/Music control. Play/pause/next/previous/stop",
            PressMediaKeyParams,
            lambda model, context: self.pressMediaKey(model, helper),
            'global'
        )

    def register_system_wide_media_actions(self, helper: PluginHelper):
        # Register system-wide media actions

        helper.register_action(
            'media_player_action',
            "Media/Music control. Play/pause/next/previous/stop",
            MediaPlayerActionParams,
            self.system_wide_media_action,
            'global'
        )

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

    def register_playlist_action(self, helper: PluginHelper):
        # Register playlist action
        # Find all playlist files
        playlists_path = os.path.join(helper.get_plugin_data_path(self.plugin_manifest), 'playlists')
        if not os.path.exists(playlists_path):
            os.makedirs(playlists_path)

        files = os.listdir(playlists_path)
        files = list(filter(lambda x: x.endswith('.m3u'), files))
        playlist_names = list(map(lambda x: x[:-4], files))
        log('debug', f"Discovered playlist names: {playlist_names}")
        if not playlist_names:
            log('debug', 'No playlists found, skipping playlist action registration.')
            return

        # Create a dynamic Pydantic model with the available playlists
        PlaylistParams = type(
            'PlaylistParams',
            (StartPlaylistParams,),
            {
                '__annotations__': {'playlist': Literal[tuple(playlist_names)]},
                'playlist': Field(description="The playlist to start playing.")
            }
        )

        helper.register_action(
            'start_playlist',
            "Start a music/media playlist by name",
            PlaylistParams,
            lambda model, context: self.start_playlist(model, helper),
            'global'
        )

    def start_playlist(self, args: StartPlaylistParams, helper: PluginHelper) -> str:
        media_playback_method = self.get_setting("media_playback_method", self.DEFAULT_PLAYBACK_METHOD, str)
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
        playlist_path: str = os.path.join(helper.get_plugin_data_path(self.plugin_manifest), 'playlists', f'{args.playlist}.m3u')
        log('debug', f"Playlist path: {playlist_path}")
        log('debug', f'Playlist file exists: {os.path.exists(playlist_path)}')
        if platform.system() == 'Darwin':       # macOS
            subprocess.call(('open', playlist_path))
        elif platform.system() == 'Windows':    # Windows
            os.startfile(playlist_path)
        else:                                   # linux variants
            subprocess.call(('xdg-open', playlist_path))

        return 'Started playlist: ' + args.playlist

    # "Shim" method. Might be moved to the base plugin class or the helper class, since it would be generally useful for any plugin that needs to update state based on external events.
    SettingValueType = TypeVar('SettingValueType')
    def get_setting(self, field_key: str, default_value: SettingValueType, cast_type: type[SettingValueType]) -> SettingValueType:
        """
        Get a plugin setting, from the settings field
        
        Args:
            field_key: The key of the field in the settings grid
            default_value: The default value to return if the setting is not found
            cast_type: The type to cast the setting value to
            
        Returns:
            The value of the setting, cast to the specified type, or the default value if not set
        """
        field_value = self.settings.get(field_key, default_value)

        if not isinstance(field_value, cast_type):
            raise TypeError(
                f"Expected {cast_type.__name__}, got {type(field_value).__name__}"
            )

        return field_value