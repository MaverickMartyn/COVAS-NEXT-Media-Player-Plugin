

from typing import Any, override

from lib.Event import Event, ProjectedEvent
from lib.Logger import log
from lib.PluginHelper import PluginEvent, Projection
from ..MediaControllerTypes import MediaPlaybackStateInner, default_media_playback_state


class CurrentMediaPlaybackState(Projection[MediaPlaybackStateInner]):
    @override
    def get_default_state(self) -> MediaPlaybackStateInner:
        return default_media_playback_state()

    @override
    def process(self, event: Event) -> list[ProjectedEvent] | None:
        log('debug', f'Processing event in CurrentMediaPlaybackState projection: {event}')
        if isinstance(event, PluginEvent) and event.plugin_event_name == "MediaPlaybackStateChangedEvent":
            event_content: dict[str, Any] = event.plugin_event_content
            self.state = MediaPlaybackStateInner(
                artist=event_content.get("artist", None),
                subtitle=event_content.get("subtitle", None),
                title=event_content.get("title", None),
                is_shuffle_active=event_content.get("is_shuffle_active", None),
                auto_repeat_mode=event_content.get("auto_repeat_mode", None),
                playback_status=event_content.get("playback_status", None)
            )
            log('debug', f'Updated media playback state: {self.state}')
            return [ProjectedEvent(content={"state": self.state.model_dump(), "event": "MediaPlaybackStateChangedEvent"})]
        return None