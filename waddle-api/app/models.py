from datetime import datetime
from enum import Enum
from typing import Optional

from nanoid import generate
from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    """Enum for processing job status"""

    init = "init"
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Episode(SQLModel, table=True):
    """Main episode model containing metadata and relationships to related resources"""

    uuid: str = Field(default_factory=generate, primary_key=True)
    preprocess_status: JobStatus = Field(default=JobStatus.init)
    edit_status: JobStatus = Field(default=JobStatus.init)
    postprocess_status: JobStatus = Field(default=JobStatus.init)
    metadata_generation_status: JobStatus = Field(default=JobStatus.init)
    export_status: JobStatus = Field(default=JobStatus.init)
    editor_state: str = Field(default="")
    title: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class EpisodeSortBy(str, Enum):
    created_at = "created_at"
    updated_at = "updated_at"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class EpisodeFilterParams(SQLModel):
    """Model for filtering episodes"""

    offset: int = Field(0, ge=0, description="Offset the number of episodes returned")
    limit: int = Field(100, gt=0, le=100, description="Limit the number of episodes returned")
    sort_by: str = Field(EpisodeSortBy.created_at, description="Sort episodes by (created_at or updated_at)")
    sort_order: SortOrder = Field(SortOrder.desc, description="Sort order (asc or desc)")
    title: Optional[str] = Field(None, description="Filter by title (partial match)")
    preprocess_status: Optional[JobStatus] = Field(None, description="Filter by preprocess status")
    edit_status: Optional[JobStatus] = Field(None, description="Filter by edit status")
    postprocess_status: Optional[JobStatus] = Field(None, description="Filter by postprocess status")
    metadata_generation_status: Optional[JobStatus] = Field(None, description="Filter by metadata generation status")
    export_status: Optional[JobStatus] = Field(None, description="Filter by export status")


class UpdateEpisodeRequest(SQLModel):
    """Model for updating an existing episode"""

    title: Optional[str] = None
    editor_state: Optional[str] = None


class JobType(str, Enum):
    """Enum for processing job types"""

    preprocess = "preprocess"
    edit = "edit"
    postprocess = "postprocess"
    metadata = "metadata"
    export = "export"


class ProcessingJob(SQLModel, table=True):
    """Represents an asynchronous processing job"""

    id: int = Field(default=None, primary_key=True)
    episode_id: str = Field(foreign_key="episode.uuid")
    type: JobType
    status: JobStatus
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None


class AnnotatedSrtContent(SQLModel):
    """Model for annotated SRT content with speaker information"""

    content: str
