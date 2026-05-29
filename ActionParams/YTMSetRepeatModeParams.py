from typing import Literal

from pydantic import BaseModel, Field

class YTMSetRepeatModeParams(BaseModel):
    repeat_mode: Literal["None", "All", "One"] = Field(
        description="The new repeat mode. 'All' to repeat the queue, 'One' to repeat the track. 'None' means no repetition."
    )
