from typing import Literal

from pydantic import BaseModel, Field

class YTMSetMuteParams(BaseModel):
    muted: bool = Field(
        description="Whether to mute the media player."
    )
