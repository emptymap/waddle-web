from datetime import datetime
from enum import Enum
from typing import Optional

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


class CreateEpisodeRequest(SQLModel):
    """Model for creating a new episode"""

    title: str


class UpdateEpisodeRequest(SQLModel):
    """Model for updating an existing episode"""

    title: Optional[str] = None
    editor_state: Optional[str] = None
    preprocessed: Optional[bool] = None
    postprocessed: Optional[bool] = None
    metadata_generated: Optional[bool] = None


class JobType(str, Enum):
    """Enum for processing job types"""

    preprocess = "preprocess"
    postprocess = "postprocess"
    metadata = "metadata"
    audio_edit = "audio_edit"


class JobStatus(str, Enum):
    """Enum for processing job status"""

    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ProcessingJob(SQLModel, table=True):
    """Represents an asynchronous processing job"""

    id: int = Field(default=None, primary_key=True)
    episode_id: str = Field(foreign_key="episode.uuid")
    type: JobType
    status: JobStatus
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None