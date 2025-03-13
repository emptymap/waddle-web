from datetime import datetime
from typing import Optional

from nanoid import generate
from sqlmodel import Field, SQLModel


class Episode(SQLModel, table=True):
    uuid: str = Field(default_factory=generate, primary_key=True)
    preprocessed: bool = Field(default=False)
    postprocessed: bool = Field(default=False)
    editor_state: str = Field(default="")
    title: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.now)


class EpisodeCreate(SQLModel):
    title: str
    editor_state: Optional[str] = ""
    preprocessed: Optional[bool] = False
    postprocessed: Optional[bool] = False


class EpisodeUpdate(SQLModel):
    title: Optional[str] = None
    editor_state: Optional[str] = None
    preprocessed: Optional[bool] = None
    postprocessed: Optional[bool] = None
