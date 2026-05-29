import json
import asyncio
import sys
from threading import Thread, Event, Timer
from typing import Any, Callable, List, Literal, Optional, cast, override
from ytmusicapi import YTMusic
import requests
import socketio
import time

from .MediaControllerTypes import MediaPlaybackStateInner, default_media_playback_state, MediaControllerBase
from lib.Logger import log

class YTMController(MediaControllerBase):
    namespace: str = "/api/v1/realtime"
    access_token: str | None = None
    _sio: socketio.Client = socketio.Client()
    _playlists_cache: list[dict[str, str]] | None = None
    current_track_opinion: Literal[-1, 0, 1, 2] = -1 # Default = Unknown.
    _deferred_state_changes: list[Timer] = []
    _ytm_client: YTMusic = YTMusic()

    def __init__(self, access_token: str | None, app_id: str, app_name: str, app_version: str, on_access_token_changed: Callable[[str], None]):
        super().__init__()
        log('info', 'App ID:', app_id)
        log('info', 'App name:', app_name)
        log('info', 'Version:', app_version)
        self.access_token = access_token
        self.app_id: str = app_id
        self.app_name: str = app_name
        self.app_version: str = app_version
        self.on_access_token_changed: Callable[[str], None] = on_access_token_changed

        self.last_media_playback_state: Optional[MediaPlaybackStateInner] = None
        asyncio.run(self.init())

    @override
    def play(self) -> str:
        if self.access_token is not None:
            return self.send_command(command='play')
        return "Error: Access has not been granted in YouTube Music Desktop Player"

    @override
    def pause(self) -> str:
        if self.access_token is not None:
            return self.send_command('pause')
        return "Error: Access has not been granted in YouTube Music Desktop Player"

    @override
    def stop(self) -> str:
        if self.access_token is not None:
            return self.send_command('pause') and self.send_command('seekTo', 0)
        return "Error: Access has not been granted in YouTube Music Desktop Player"

    @override
    def prev_track(self) -> str:
        if self.access_token is not None:
            return self.send_command('previous')
        return "Error: Access has not been granted in YouTube Music Desktop Player"

    @override
    def next_track(self) -> str:
        if self.access_token is not None:
            return self.send_command('next')
        return "Error: Access has not been granted in YouTube Music Desktop Player"

    @override
    def get_media_playback_state(self) -> MediaPlaybackStateInner: return self.last_media_playback_state or default_media_playback_state()

    @override
    def cleanup(self):
        self._sio.shutdown()
        if self._playlists_cache:
            self._playlists_cache.clear()

    @override
    def start_playlist(self, path: str) -> str:
        playlists = self.get_playlists()
        for playlist in playlists:
            if playlist['title'] == path:
                return self.send_command('changeVideo', data={"playlistId": playlist['id']})
        return "Playlist not found."

    def send_command(self, command: str, data: Any = None) -> str:
        try:
            url = "http://localhost:9863/api/v1/command"  # Change host/port if needed

            payload = {
                "command": command
            }
            if data is not None:
                payload["data"] = data

            headers = {
                'Authorization': self.access_token
            }
            response = requests.post(url, json=payload, headers=headers)

            if len(response.content) > 0:
                content: dict = response.json()
                log('info', f"Response JSON: {content}")
                if 'error' in content.keys():
                    log('error', f"Failed to send command '{command}': {content['error']}")
                    return content['error']
            if not response.ok:
                return f"An unknown internal error occured in YTMController. Status Code: {response.status_code}"
            return "Success."
        except Exception as e:
            log('error', f"Failed to send command '{command}': {e}")
            return "An unknown internal error occured in YTMController."

    def get_code(self) -> str:
        url = "http://localhost:9863/api/v1/auth/requestcode"  # Change host/port if needed

        payload = {
            "appId": self.app_id,
            "appName": self.app_name,
            "appVersion": self.app_version
        }

        response = requests.post(url, json=payload)
        content = response.json()
        return content['code']

    def get_auth(self, code: str) -> str:
        url = "http://localhost:9863/api/v1/auth/request"  # Change host/port if needed

        payload = {
            "appId": self.app_id,
            "code": code,
        }

        response = requests.post(url, json=payload)
        content = response.json()
        return content['token']

    def get_state(self, data) -> MediaPlaybackStateInner:
        if not self._sio.connected or data is None:
            log('debug', 'Not connected to YTM Desktop Player, returning default state')
            return default_media_playback_state()
        # log('info', "🔄 State updated:", data)

        repeat_mode = "None"
        if data['player']['queue']['repeatMode'] == 1:
            repeat_mode = "All"
        elif data['player']['queue']['repeatMode'] == 2:
            repeat_mode = "One"

        playback_status = "Unknown" # -1
        if data['player']['trackState'] == 0 or data['player']['trackState'] == 2 or data['player']['trackState'] == -1: # Paused (0), buffering (2) or explicitly Unknown.
            playback_status = "Paused"
        elif data['player']['trackState'] == 1:
            playback_status = "Playing"

        state = MediaPlaybackStateInner(
            artist=data['video']['author'],
            subtitle=data['video']['album'],
            title=data['video']['title'],
            is_shuffle_active=None,
            is_muted=data['player']['muted'],
            auto_repeat_mode=repeat_mode,
            playback_status=playback_status,
            volume=data['player']['volume'])

        return state
    
    async def init(self):
        if self.access_token is None:
            log('warn', 'Missing YouTube Music Desktop player access. Requesting code...')
            code = self.get_code()
            # TODO: Report this code to the user through the AI, since YouTube Music Desktop Player asks for it, instead of just logging it.
            if code == "AUTHORIZATION_DISABLED":
                log('error', 'Authorization is disabled in YouTube Music Desktop Player. Please enable it in the player settings and restart the plugin.')
                # TODO: Add proper reporting of this error to the user, through the AI.
                return
            log('info', f'Requested access to YouTube Music Desktop Player. Code: {code}')
            self.access_token = self.get_auth(code)
            log('info', 'YouTube Music Desktop Player access obtained.')
            self.on_access_token_changed(self.access_token)

        self._sio.connect(
            "http://127.0.0.1:9863",
            transports=["websocket"],
            auth={"token": self.access_token},
            namespaces=[self.namespace]
        )

        @self._sio.on("state-update", namespace=self.namespace)
        def on_state_update(data):
            state = self.get_state(data)

            if self.last_media_playback_state == state:
                return

            # If the only change is the playback_status, defer the state change in case we're changing tracks.
            if (self.only_playback_status_has_changed_to_pause(self.last_media_playback_state or default_media_playback_state(), state)):
                # Defer event for a quarter of a second.
                log('info', 'deferring state change')
                timer = Timer(1, function = self._process_defered_state, args = (data, state))
                self._deferred_state_changes.append(timer)
                timer.start()
                return
            
            # Cancel any deferred state changes.
            if len(self._deferred_state_changes):
                log('info', 'clearing deferred state changes')
                for deferred_state in self._deferred_state_changes:
                    deferred_state.cancel()
                self._deferred_state_changes = []

            self._update_state(data, state)

        @self._sio.on("playlist-created", namespace=self.namespace)
        def on_playlist_created(data):
            if self._playlists_cache is None:
                self._playlists_cache = self.get_playlists()
            if data in self._playlists_cache:
                return
            self._playlists_cache.insert(0, data)

        @self._sio.on("playlist-delete", namespace=self.namespace)
        def on_playlist_delete(data):
            if self._playlists_cache is None:
                self._playlists_cache = self.get_playlists()
            if data in self._playlists_cache:
                self._playlists_cache.remove(data)

    def get_playlists(self) -> list[dict[str, str]]:
        if self._playlists_cache is None:
            url = "http://localhost:9863/api/v1/playlists"

            headers = {
                'Authorization': self.access_token
            }
            response = requests.get(url, headers=headers)
            content = response.json()
            self._playlists_cache = cast(list[dict[str, str]], content)
        return self._playlists_cache

    def play_by_search(self, query: str) -> str:
        log('info', f"Searching YouTube Music for '{query}'.")
        results = self._ytm_client.search(query)
        no_result = f"No results found for '{query}'."
        if len(results) > 0:
            for result in results:
                ret_val = no_result
                # Find the first valid result
                keys = result.keys()
                if 'videoId' in keys:
                    ret_val = self.send_command('changeVideo', data={"videoId": result['videoId']})
                elif 'playlistId' in keys:
                    ret_val = self.send_command('changeVideo', data={"playlistId": result['playlistId']})
                else:
                    continue

                if ret_val != "Success.":
                    return ret_val
                return f"Playing '{result["title"]}'."
        return no_result

    def set_volume(self, level: int) -> str:
        return self.send_command('setVolume', level)

    def set_mute(self, is_muted: bool) -> str:
        if is_muted:
            return self.send_command('mute')
        else:
            return self.send_command('unmute')

    def toggle_shuffle(self) -> str:
        return self.send_command('shuffle')

    def set_repeat_mode(self, mode: Literal["None", "All", "One"]) -> str:
        mode_int = 0 # None
        if mode == "All":
            mode_int = 1
        elif mode == "One":
            mode_int = 2
        return self.send_command('repeatMode', mode_int)

    def set_opinion(self, opinion: Literal['Like', 'Dislike', 'Indifferent']) -> str:
        if opinion == 'Like' and self.current_track_opinion != 2: # Only toggle if it isn't already liked.
            return self.send_command('toggleLike')
        elif opinion == 'Dislike' and self.current_track_opinion != 0: # Only toggle if it isn't already disliked.
            return self.send_command('toggleDislike')

        ret_val: str | None = None
        if opinion == 'Indifferent' and self.current_track_opinion == 2: # Only toggle if it it's liked.
            ret_val = self.send_command('toggleLike')
        if ret_val is None and opinion == 'Indifferent' and self.current_track_opinion == 1: # Only toggle if it it's disliked.
            ret_val = self.send_command('toggleDislike')
        return "An unknown error occured while setting track opinion." if ret_val is None else ret_val
    
    @staticmethod
    def only_playback_status_has_changed_to_pause(old_state: MediaPlaybackStateInner, new_state: MediaPlaybackStateInner) -> bool:
        # Separate PlaybackStatus from the rest of the state
        old_status = old_state.playback_status
        new_status = new_state.playback_status

        # Copy the states excluding playback_status
        old_meta = {k: v for k, v in old_state.model_dump().items() if k != "playback_status"}
        new_meta = {k: v for k, v in new_state.model_dump().items() if k != "playback_status"}

        # If the metadata is identical, and status has changed to 'Paused', return True
        return old_meta == new_meta and old_status != new_status and new_state.playback_status == "Paused"

    def _update_state(self, data, state: MediaPlaybackStateInner):
        self.last_media_playback_state = state
        
        if data['video'] is not None:
            self.current_track_opinion = data['video']['likeStatus'] or -1

        if self.on_media_playback_info_changed is not None:
            self.on_media_playback_info_changed(state)
    
    def _process_defered_state(self, data, new_state: MediaPlaybackStateInner):
        self._update_state(data, new_state)
