from typing import Literal

from pydantic import BaseModel, Field

class YTMSetTrackOpinionParams(BaseModel):
    opinion: Literal["Like", "Dislike", "Indifferent"] = Field(description="Indicates the user's opinion.")