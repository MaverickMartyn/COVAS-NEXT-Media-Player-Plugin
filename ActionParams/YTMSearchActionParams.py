from typing import Literal

from pydantic import BaseModel, Field

class YTMSearchActionParams(BaseModel):
    query: str = Field(
        description="The search query."
    )
