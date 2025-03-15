# Waddle-API Design Document

## Overview
This document outlines the API specification for a podcast editing web application backend that integrates with the Waddle preprocessing library. The system will handle audio file processing, transcription, editing, and final export functionality including metadata and chapter generation.

## API Endpoints

### 1. Episode Management

#### 1.1 Create Episode
- **Endpoint**: `POST /api/v1/episodes`
- **Description**: Creates a new episode and initiates preprocessing
- **Request Body**: `EpisodeCreate` model
  ```typescript
  {
    title: string;
  }
  ```
- **Request Files**: Audio files (multipart/form-data)
- **Response**: `Episode` model

#### 1.2 Get Episode
- **Endpoint**: `GET /api/v1/episodes/{uuid}`
- **Description**: Retrieves episode metadata and status
- **Response**: `Episode` model (same as Create Episode response)

#### 1.3 Update Episode
- **Endpoint**: `PUT /api/v1/episodes/{uuid}`
- **Description**: Updates episode metadata and editor state
- **Request Body**: `EpisodeUpdate` model
  ```typescript
  {
    title?: string;
    editor_state?: string;
    preprocessed?: boolean;
    postprocessed?: boolean;
    metadata_generated?: boolean;
  }
  ```
- **Response**: `Episode` model

### 2. Audio Processing

#### 2.1 Get Preprocessed Audio Files
- **Endpoint**: `GET /api/v1/episodes/{uuid}/audios`
- **Description**: Retrieves all preprocessed audio files
- **Response**: List of `ProcessedFile` models

#### 2.2 Get Single Audio File
- **Endpoint**: `GET /api/v1/episodes/{uuid}/audio/{file_id}`
- **Description**: Retrieves a specific audio file
- **Response**: Audio file stream

#### 2.3 Get Transcription
- **Endpoint**: `GET /api/v1/episodes/{uuid}/srt`
- **Description**: Retrieves SRT transcription file
- **Response**: SRT file stream

### 3. Post-Processing

#### 3.1 Initiate Post-Processing
- **Endpoint**: `POST /api/v1/episodes/{uuid}/postprocess`
- **Description**: Initiates Waddle postprocessing with current editor state
- **Request Body**: `PostProcessRequest` model
  ```typescript
  {
    whisper_options?: string; // Optional Whisper options
    no_noise_remove?: boolean; // Optional, default: false
  }
  ```

#### 3.2 Get Post-Processed Audio
- **Endpoint**: `GET /api/v1/episodes/{uuid}/postprocessed-audio`
- **Description**: Retrieves the final post-processed audio
- **Response**: Audio file stream

### 4. Transcription Management

#### 4.1 Get Annotated SRT
- **Endpoint**: `GET /api/v1/episodes/{uuid}/annotated-srt`
- **Description**: Retrieves annotated SRT with speaker information
- **Response**: `AnnotatedSrtContent` model

#### 4.2 Update Annotated SRT
- **Endpoint**: `PUT /api/v1/episodes/{uuid}/annotated-srt`
- **Description**: Updates annotated SRT
- **Request Body**: `AnnotatedSrtContent` model
  ```typescript
  {
    content: string; // SRT content with annotations
  }
  ```
- **Response**: `AnnotatedSrtContent` model

### 5. Metadata Generation

#### 5.1 Generate Metadata
- **Endpoint**: `POST /api/v1/episodes/{uuid}/metadata`
- **Description**: Generates chapter information and show notes from annotated SRT
- **Request Body**: `MetadataGenerationRequest` model
  ```typescript
  {
    audio_file_id?: number; // Optional specific audio file ID to use
  }
  ```

#### 5.2 Get Chapter Information
- **Endpoint**: `GET /api/v1/episodes/{uuid}/chapters`
- **Description**: Retrieves chapter information in text format
- **Response**: Chapter file content

#### 5.3 Get Show Notes
- **Endpoint**: `GET /api/v1/episodes/{uuid}/show-notes`
- **Description**: Retrieves generated show notes in markdown format
- **Response**: Show notes content

### 6. Export

#### 6.1 Export Final Files
- **Endpoint**: `POST /api/v1/episodes/{uuid}/export`
- **Description**: Generates final MP3, metadata, chapters, and SRT
- **Request Body**: `ExportRequest` model
  ```typescript
  {
    embed_chapters?: boolean; // Optional, default: true
    include_show_notes?: boolean; // Optional, default: true
    format?: string; // Optional: "mp3" | "wav", default: "mp3"
  }
  ```

#### 6.2 Download Exported Files
- **Endpoint**: `GET /api/v1/episodes/{uuid}/export/{file_type}`
- **Description**: Downloads specific export file (mp3, metadata, chapters, srt)
- **Path Parameters**: file_type: "mp3" | "chapters" | "show_notes" | "srt"
- **Response**: File stream

### 7. Audio Editing

#### 7.1 Apply Audio Edits
- **Endpoint**: `POST /api/v1/episodes/{uuid}/audio-edits`
- **Description**: Applies edits to audio files based on specified time ranges
- **Request Body**: Skeleton for audio edits (implementation depends on web interface needs)

#### 7.2 Get Edited Audio Files
- **Endpoint**: `GET /api/v1/episodes/{uuid}/edited-audio`
- **Description**: Retrieves all edited audio files
- **Response**: List of `ProcessedFile` models


## Data Models

```python
from datetime import datetime
from typing import Optional, List, Literal
from nanoid import generate
from sqlmodel import Field, SQLModel, Relationship
from pydub import AudioSegment

# Import type definitions from Waddle
from waddle.processing.combine import SpeechSegment, SpeechTimeline, SrtEntry, SrtEntries
from waddle import EditorState

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
    
    # New fields
    storage_path: str = Field(default="")
    source_files: List["SourceFile"] = Relationship(back_populates="episode")
    processed_files: List["ProcessedFile"] = Relationship(back_populates="episode")
    transcriptions: List["Transcription"] = Relationship(back_populates="episode")
    metadata_files: List["MetadataFile"] = Relationship(back_populates="episode")

class EpisodeCreate(SQLModel):
    """Model for creating a new episode"""
    title: str

class EpisodeUpdate(SQLModel):
    """Model for updating an existing episode"""
    title: Optional[str] = None
    editor_state: Optional[str] = None
    preprocessed: Optional[bool] = None
    postprocessed: Optional[bool] = None
    metadata_generated: Optional[bool] = None

class SourceFile(SQLModel, table=True):
    """
    Represents an original audio file uploaded by the user.
    
    There are two types of source files:
    1. Reference files (is_reference=True): Usually a recording from Zoom or other software 
       that contains all speakers. File names start with 'GMT'.
    2. Speaker-specific files (is_reference=False): Individual audio tracks for each speaker.
       These files have speaker names embedded in their file names (e.g., 'ep1-Alice.wav').
    
    These files serve as inputs to the preprocessing stage before they are aligned and normalized.
    """
    id: int = Field(default=None, primary_key=True)
    episode_id: str = Field(foreign_key="episode.uuid")
    filename: str
    file_path: str
    speaker_name: Optional[str] = None
    is_reference: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    
    episode: Episode = Relationship(back_populates="source_files")

class ProcessedFile(SQLModel, table=True):
    """Represents a processed audio file after preprocessing, editing, or postprocessing"""
    id: int = Field(default=None, primary_key=True)
    episode_id: str = Field(foreign_key="episode.uuid")
    filename: str
    file_path: str
    file_type: str  # "preprocessed", "postprocessed", "export"
    speaker_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    episode: Episode = Relationship(back_populates="processed_files")

class Transcription(SQLModel, table=True):
    """Represents an SRT transcription file, either generated or annotated"""
    id: int = Field(default=None, primary_key=True)
    episode_id: str = Field(foreign_key="episode.uuid")
    file_path: str
    is_annotated: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    episode: Episode = Relationship(back_populates="transcriptions")

class Chapter(SQLModel, table=True):
    """Represents a chapter marker in the episode"""
    id: int = Field(default=None, primary_key=True)
    episode_id: str = Field(foreign_key="episode.uuid")
    title: str
    start_time: float  # in seconds
    end_time: float  # in seconds
    level: int
    
    episode: Episode = Relationship()

class MetadataFile(SQLModel, table=True):
    """Represents metadata files such as chapter lists and show notes"""
    id: int = Field(default=None, primary_key=True)
    episode_id: str = Field(foreign_key="episode.uuid")
    file_path: str
    file_type: str  # "chapters", "show_notes"
    created_at: datetime = Field(default_factory=datetime.now)
    
    episode: Episode = Relationship(back_populates="metadata_files")

class ProcessingJob(SQLModel, table=True):
    """Represents an asynchronous processing job"""
    id: int = Field(default=None, primary_key=True)
    episode_id: str = Field(foreign_key="episode.uuid")
    job_type: Literal["preprocess", "postprocess", "metadata", "export", "audio_edit"]
    status: Literal["pending", "processing", "completed", "failed"]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None

# Request/Response Models

class PostProcessRequest(SQLModel):
    """Model for initiating post-processing"""
    whisper_options: Optional[str] = None
    no_noise_remove: Optional[bool] = False

class MetadataGenerationRequest(SQLModel):
    """Model for initiating metadata generation"""
    audio_file_id: Optional[int] = None

class ExportRequest(SQLModel):
    """Model for initiating export"""
    embed_chapters: Optional[bool] = True
    include_show_notes: Optional[bool] = True
    format: Optional[str] = "mp3"  # "mp3", "wav"

class AnnotatedSrtContent(SQLModel):
    """Model for updating annotated SRT"""
    content: str

class AnnotatedSrtUpdateResponse(SQLModel):
    """Model for response after updating annotated SRT"""
    success: bool
    id: int
    episode_id: str
    is_annotated: bool
    updated_at: datetime

```

## Implementation Guide

### Storage Structure

Episodes will be stored in a hierarchical directory structure:
```
{user_runtime_dir}/{APP_NAME}/{APP_AUTHOR}/episodes/{episode_uuid}/
├── source/                  # Original uploaded files
├── preprocessed/            # Aligned and normalized audio files
│   ├── speaker1.wav
│   ├── speaker2.wav
│   └── transcript.srt
├── postprocessed/           # Edited audio files
│   ├── final.wav
│   ├── transcript.srt
│   └── annotated.srt
└── export/                  # Final deliverable files
    ├── episode.mp3
    ├── chapters.txt
    ├── show_notes.md
    └── transcript.srt
```

### Sample Implementation

```python
from pathlib import Path
import shutil
from platformdirs import user_runtime_dir
from fastapi import BackgroundTasks, UploadFile, Depends, HTTPException
from sqlmodel import Session, select
from waddle import EditorState
from waddle.processing import preprocess_multi_files, apply_edits, generate_metadata

# Episode creation
async def create_episode(
    episode_data: EpisodeCreate, 
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    db: Session
):
    # Create episode record
    new_episode = Episode(**episode_data.dict())
    
    # Set up storage directories
    storage_path = Path(user_runtime_dir(APP_NAME, APP_AUTHOR)) / "episodes" / new_episode.uuid
    storage_path.mkdir(parents=True, exist_ok=True)
    new_episode.storage_path = str(storage_path)
    
    # Save uploaded files and create entries
    source_dir = storage_path / "source"
    source_dir.mkdir(exist_ok=True)
    
    source_files = []
    reference_file = None
    
    for file in files:
        file_path = source_dir / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Handle file categorization logic
        is_reference = file.filename.startswith("GMT")
        speaker_name = extract_speaker_name(file.filename) if not is_reference else None
        
        source_file = SourceFile(
            episode_id=new_episode.uuid,
            filename=file.filename,
            file_path=str(file_path),
            speaker_name=speaker_name,
            is_reference=is_reference
        )
        source_files.append(source_file)
        
        if is_reference:
            reference_file = source_file
    
    # Save all to database
    db.add(new_episode)
    for sf in source_files:
        db.add(sf)
    db.commit()
    db.refresh(new_episode)
    
    # Start preprocessing in background
    job = ProcessingJob(
        episode_id=new_episode.uuid,
        job_type="preprocess",
        status="pending"
    )
    db.add(job)
    db.commit()
    
    background_tasks.add_task(
        run_preprocessing,
        job.id,
        new_episode.uuid,
        source_files,
        reference_file
    )
    
    return new_episode

# Background preprocessing task
async def run_preprocessing(
    job_id: int,
    episode_uuid: str,
    source_files: list[SourceFile],
    reference_file: SourceFile
):
    db = get_db_session()
    
    # Update job status
    job = db.get(ProcessingJob, job_id)
    job.status = "processing"
    db.commit()
    
    try:
        # Get episode
        episode = db.get(Episode, episode_uuid)
        source_dir = Path(episode.storage_path) / "source"
        output_dir = Path(episode.storage_path) / "preprocessed"
        output_dir.mkdir(exist_ok=True)
        
        # Prepare parameters for Waddle preprocessing
        reference_path = Path(reference_file.file_path) if reference_file else None
        
        # Run Waddle preprocessing function
        processed_files = preprocess_multi_files(
            reference=reference_path,
            source_dir=source_dir,
            output_dir=output_dir,
            generate_transcript=True
        )
        
        # Save processed file references to database
        for proc_file in processed_files:
            processed_file = ProcessedFile(
                episode_id=episode_uuid,
                filename=proc_file.name,
                file_path=str(proc_file),
                file_type="preprocessed",
                speaker_name=extract_speaker_name(proc_file.name)
            )
            db.add(processed_file)
        
        # Add transcription record
        srt_path = output_dir / "transcript.srt"
        if srt_path.exists():
            transcription = Transcription(
                episode_id=episode_uuid,
                file_path=str(srt_path),
                is_annotated=False
            )
            db.add(transcription)
        
        # Update episode status
        episode.preprocessed = True
        
        # Update job status
        job.status = "completed"
        
    except Exception as e:
        # Handle errors
        job.status = "failed"
        job.error_message = str(e)
        
    finally:
        db.commit()
        db.close()
```
