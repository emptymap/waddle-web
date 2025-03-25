import shutil
from pathlib import Path
from typing import Annotated, List

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from platformdirs import user_data_dir
from sqlmodel import Session, select
from waddle.processor import preprocess_multi_files

from app.db import get_session
from app.defaults import APP_AUTHOR, APP_NAME
from app.models import Episode, JobStatus, JobType, ProcessingJob, UpdateEpisodeRequest

SessionDep = Annotated[Session, Depends(get_session)]
app_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))

# Create v1 router
v1_router = APIRouter(tags=["v1"])


# Episode CRUD endpoints
@v1_router.get("/episodes/", response_model=List[Episode])
def read_episodes(
    session: SessionDep,
    offset: Annotated[int, Query(ge=0, description="Offset the number of episodes returned")] = 0,
    limit: Annotated[int, Query(le=100, description="Limit the number of episodes returned")] = 100,
) -> List[Episode]:
    """Read all episodes"""
    episodes = session.exec(select(Episode).offset(offset).limit(limit)).all()
    return list(episodes)


@v1_router.post(
    "/episodes/",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "No file name provided"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error"},
    },
)
async def create_episode(
    files: list[UploadFile], db: SessionDep, background_tasks: BackgroundTasks, title: Annotated[str, Form(description="Episode title")] = ""
) -> Episode:
    new_episode = Episode(title=title, preprocess_status=JobStatus.pending)

    storage_path = app_dir / "episodes" / new_episode.uuid
    storage_path.mkdir(parents=True, exist_ok=True)

    source_dir = storage_path / "source"
    source_dir.mkdir(exist_ok=True)
    try:
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file name provided")
            file_path = source_dir / file.filename
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
        db.add(new_episode)
        job = ProcessingJob(episode_id=new_episode.uuid, type=JobType.preprocess, status=JobStatus.pending)
        db.add(job)
        db.commit()

        background_tasks.add_task(run_preprocessing, job.id, new_episode.uuid, db)
        return new_episode
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


# Background preprocessing task
def run_preprocessing(job_id: int, episode_uuid: str, db: Session) -> None:
    job = db.get(ProcessingJob, job_id)
    if not job:
        return
    episode = db.get(Episode, episode_uuid)
    if not episode:
        return
    episode.preprocess_status = JobStatus.processing
    job.status = JobStatus.processing
    db.commit()
    db.refresh(episode)
    db.refresh(job)
    try:
        episode_dir = app_dir / "episodes" / episode_uuid
        preprocess_multi_files(reference=None, source_dir=episode_dir / "source", output_dir=episode_dir / "preprocessed", transcribe=True)
        episode.preprocess_status = JobStatus.completed
        job.status = JobStatus.completed
    except Exception as e:
        episode.preprocess_status = JobStatus.failed
        job.status = JobStatus.failed
        job.error_message = str(e)
    finally:
        db.commit()
        db.refresh(episode)
        db.refresh(job)
        db.close()


@v1_router.get(
    "/episodes/{episode_id}",
    response_model=Episode,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode not found"},
    },
)
def get_episode(episode_id: str, session: SessionDep) -> Episode:
    """Get a specific episode by ID"""
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return episode


@v1_router.patch(
    "/episodes/{episode_id}",
    response_model=Episode,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Episode not found"},
    },
)
def update_episode(episode_id: str, update_data: UpdateEpisodeRequest, session: SessionDep) -> Episode:
    """Update an existing episode"""
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    if update_data.title is not None:
        episode.title = update_data.title
    if update_data.editor_state is not None:
        episode.editor_state = update_data.editor_state

    session.add(episode)
    session.commit()
    session.refresh(episode)
    return episode


@v1_router.delete("/episodes/{episode_id}", status_code=status.HTTP_204_NO_CONTENT, responses={status.HTTP_404_NOT_FOUND: {"description": "Episode not found"}})
def delete_episode(episode_id: str, session: SessionDep) -> None:
    """Delete an episode"""
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    session.delete(episode)
    session.commit()

    episode_dir = app_dir / "episodes" / episode_id
    if episode_dir.exists():
        shutil.rmtree(episode_dir)

    return None  # Using 204 No Content for successful deletion


# Helper function to check if preprocessing is completed
def check_preprocessing_completed(episode: Episode) -> None:
    """Check if preprocessing is completed for an episode"""
    if episode.preprocess_status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Episode preprocessing is not completed. Current status: {episode.preprocess_status}"
        )


@v1_router.get("/episodes/{episode_id}/audios", response_model=List[str])
def get_preprocessed_audio_files(episode_id: str, session: SessionDep) -> List[str]:
    """Retrieves all preprocessed audio filenames for a specific episode"""
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    check_preprocessing_completed(episode)

    preprocessed_dir = app_dir / "episodes" / episode_id / "preprocessed"
    if not preprocessed_dir.exists():
        return []

    audio_files: List[str] = []
    for file_path in preprocessed_dir.glob("*.wav"):
        audio_files.append(file_path.name)
    return audio_files


@v1_router.get(
    "/episodes/{episode_id}/audio/{file_name}",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Audio file or episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode preprocessing not completed"},
    },
)
def get_audio_file(episode_id: str, file_name: str, session: SessionDep) -> FileResponse:
    """Retrieves a specific audio file"""
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    check_preprocessing_completed(episode)

    audio_file_path = app_dir / "episodes" / episode_id / "preprocessed" / file_name
    if not audio_file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")

    return FileResponse(path=audio_file_path, media_type="audio/wav", filename=audio_file_path.name)


@v1_router.get(
    "/episodes/{episode_id}/srt",
    response_model=str,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "SRT file or episode not found"},
        status.HTTP_400_BAD_REQUEST: {"description": "Episode preprocessing not completed"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Error reading SRT file"},
    },
)
def get_transcription(episode_id: str, session: SessionDep) -> str:
    """Retrieves SRT transcription file content as a string"""
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    check_preprocessing_completed(episode)

    preprocessed_dir = app_dir / "episodes" / episode_id / "preprocessed"
    srt_files = list(preprocessed_dir.glob("*.srt"))
    if not srt_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SRT file not found")

    srt_file_path = srt_files[0]

    try:
        with open(srt_file_path, "r", encoding="utf-8") as file:
            srt_content = file.read()
        return srt_content
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error reading SRT file: {str(e)}") from e
