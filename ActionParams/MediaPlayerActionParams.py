from typing import Literal

from pydantic import BaseModel, Field

class MediaPlayerActionParams(BaseModel):
    action: Literal["play", "pause", "next", "previous", "stop"] = Field(
        description="The media player function."
    )
