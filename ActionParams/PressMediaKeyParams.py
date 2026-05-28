from typing import Literal

from pydantic import BaseModel, Field

class PressMediaKeyParams(BaseModel):
    key: Literal["play_pause", "next", "previous", "stop"] = Field(
        description="The media key to press."
    )