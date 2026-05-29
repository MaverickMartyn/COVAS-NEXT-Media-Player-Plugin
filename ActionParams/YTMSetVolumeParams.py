from typing import Literal

from pydantic import BaseModel, Field

class YTMSetVolumeParams(BaseModel):
    level: int = Field(
        description="The volume level (0-100)."
    )
