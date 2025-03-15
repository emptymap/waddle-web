from datetime import datetime

from nanoid import generate
from sqlmodel import Field, SQLModel


class Episode(SQLModel, table=True):
    """Main episode model containing metadata and relationships to related resources"""

    uuid: str = Field(default_factory=generate, primary_key=True)
    preprocessed: bool = Field(default=False)
    postprocessed: bool = Field(default=False)
    metadata_generated: bool = Field(default=False)
    editor_state: str = Field(default="")
    title: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
