from pydantic import BaseModel, Field


class StartPlaylistParams(BaseModel):
    playlist: str = Field(
        description="The playlist to start playing."
    )